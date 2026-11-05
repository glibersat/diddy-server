import asyncio
from datetime import datetime, timedelta, UTC

import pytest

from app.models import AckAction, Notification, NotificationChannel, NotificationStatus, ReminderKind, RuleType, User
from app.notify import dispatcher
from app.notify.ack import record_ack, record_delivered


class FakeConnectionManager:
    """Stands in for the real WebSocket ConnectionManager: records what was "sent"."""

    def __init__(self, connected_users: set[str]):
        self.connected_users = connected_users
        self.sent: list[tuple[str, dict]] = []

    def is_connected(self, user_id: str) -> bool:
        return user_id in self.connected_users

    async def send_to_user(self, user_id: str, payload: dict) -> bool:
        if user_id not in self.connected_users:
            return False
        self.sent.append((user_id, payload))
        return True


def _pending_notification(user_id: str, dedupe_key: str = "d1") -> Notification:
    return Notification(
        user_id=user_id,
        rule_type=RuleType.daily_schedule,
        rule_id="rule-1",
        dedupe_key=dedupe_key,
        scheduled_for=datetime.now(UTC),
        title="Reminder",
        body="Take meds",
        kind=ReminderKind.medication,
        dismissible=False,
        snooze_minutes=[5, 15],
    )


def _pending_alert(user_id: str, dedupe_key: str = "a1") -> Notification:
    return Notification(
        user_id=user_id,
        rule_type=RuleType.ics_reminder,
        rule_id="source-1",
        dedupe_key=dedupe_key,
        scheduled_for=datetime.now(UTC),
        title="In 15 min: Dentist",
        body="In 15 min: Dentist (14:30)",
        channel=NotificationChannel.alert,
    )


@pytest.mark.asyncio
async def test_dispatch_pending_sends_alert_payload(db_session, user, monkeypatch):
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)

    db_session.add(_pending_alert(user.id))
    db_session.commit()

    created = await dispatcher.dispatch_pending(db_session)

    assert created == 1
    assert fake.sent[0][1] == {"type": "alert", "message": "In 15 min: Dentist (14:30)"}


def test_requeue_undelivered_retries_alert_channel_same_as_reminder(db_session, user, monkeypatch):
    monkeypatch.setattr(dispatcher.settings, "delivery_timeout_seconds", 60)
    notification = _pending_alert(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=120)
    notification.send_attempts = 1
    db_session.add(notification)
    db_session.commit()

    requeued = dispatcher.requeue_undelivered(db_session)

    assert requeued == 1
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.pending


def test_record_delivered_closes_out_alert_channel_without_a_separate_ack(db_session, user):
    notification = _pending_alert(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC)
    db_session.add(notification)
    db_session.commit()

    delivered = record_delivered(db_session, user.id)

    assert delivered.delivered_at is not None
    assert delivered.status == NotificationStatus.acked

    # And requeue_unacked must not try to nag an alert that will never be acked.
    far_future = datetime.now(UTC) + timedelta(days=1)
    assert dispatcher.requeue_unacked(db_session, now=far_future) == 0


@pytest.mark.asyncio
async def test_dispatch_pending_sends_and_marks_sent(db_session, user, monkeypatch):
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)

    notification = _pending_notification(user.id)
    db_session.add(notification)
    db_session.commit()

    created = await dispatcher.dispatch_pending(db_session)

    assert created == 1
    assert fake.sent[0][1]["title"] == "Reminder"
    assert fake.sent[0][1]["easyDismiss"] is False
    assert fake.sent[0][1]["snoozeMinutes"] == [5, 15]
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.sent
    assert notification.send_attempts == 1


@pytest.mark.asyncio
async def test_dispatch_pending_leaves_offline_users_pending_without_spending_attempts(db_session, user, monkeypatch):
    """No socket isn't a send attempt - otherwise a phone offline for a minute or so would burn
    the whole max_send_attempts budget on ticks that never reached anything."""
    fake = FakeConnectionManager(connected_users=set())  # nobody connected
    monkeypatch.setattr(dispatcher, "manager", fake)
    monkeypatch.setattr(dispatcher.settings, "max_send_attempts", 2)

    notification = _pending_notification(user.id)
    db_session.add(notification)
    db_session.commit()

    for _ in range(5):
        assert await dispatcher.dispatch_pending(db_session) == 0
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.pending
    assert notification.send_attempts == 0


class FailingSocketManager(FakeConnectionManager):
    """Connected, but every send fails (the dead socket gets dropped mid-send)."""

    async def send_to_user(self, user_id: str, payload: dict) -> bool:
        return False


@pytest.mark.asyncio
async def test_dispatch_pending_fails_after_max_failed_sends(db_session, user, monkeypatch):
    fake = FailingSocketManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)
    monkeypatch.setattr(dispatcher.settings, "max_send_attempts", 2)

    notification = _pending_notification(user.id)
    db_session.add(notification)
    db_session.commit()

    await dispatcher.dispatch_pending(db_session)
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.pending  # attempt 1, still retrying

    await dispatcher.dispatch_pending(db_session)
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.failed  # attempt 2 == max, gives up


@pytest.mark.asyncio
async def test_delivered_arriving_mid_dispatch_matches_the_row_just_sent(db_session, user, monkeypatch):
    """The phone's `delivered` can come back while dispatch is still awaiting later sends - the
    row has to already be `sent` by then, or the confirmation is dropped."""

    class ConfirmingManager(FakeConnectionManager):
        async def send_to_user(self, user_id: str, payload: dict) -> bool:
            await super().send_to_user(user_id, payload)
            self.confirmed.append(record_delivered(db_session, user_id))
            return True

    fake = ConfirmingManager(connected_users={user.id})
    fake.confirmed = []
    monkeypatch.setattr(dispatcher, "manager", fake)

    db_session.add_all([_pending_notification(user.id, "d1"), _pending_notification(user.id, "d2")])
    db_session.commit()

    assert await dispatcher.dispatch_pending(db_session) == 2
    assert all(n is not None for n in fake.confirmed)
    assert len({n.id for n in fake.confirmed}) == 2


@pytest.mark.asyncio
async def test_concurrent_dispatch_sends_each_notification_once(db_session, user, monkeypatch):
    """`_dispatch_tick` and a `watch_ready`-driven `resend_now` for the same user can overlap."""

    class YieldingManager(FakeConnectionManager):
        async def send_to_user(self, user_id: str, payload: dict) -> bool:
            await asyncio.sleep(0)  # let the other dispatcher run mid-send, like a real socket
            return await super().send_to_user(user_id, payload)

    fake = YieldingManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)

    db_session.add_all([_pending_notification(user.id, "d1"), _pending_notification(user.id, "d2")])
    db_session.commit()

    await asyncio.gather(dispatcher.dispatch_pending(db_session), dispatcher.dispatch_pending(db_session))

    assert len(fake.sent) == 2


@pytest.mark.asyncio
async def test_dispatch_pending_sends_oldest_first(db_session, user, monkeypatch):
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)

    older = _pending_notification(user.id, "old")
    older.body = "first"
    older.created_at = datetime.now(UTC) - timedelta(minutes=1)
    newer = _pending_notification(user.id, "new")
    newer.body = "second"
    db_session.add_all([newer, older])
    db_session.commit()

    await dispatcher.dispatch_pending(db_session)

    assert [payload["body"] for _, payload in fake.sent] == ["first", "second"]


@pytest.mark.asyncio
async def test_record_ack_goes_to_last_reminder_of_a_dispatch_batch(db_session, user, monkeypatch):
    """The watch shows only the last trigger it got, so that's what the wearer is acking - not
    an arbitrary row out of a batch that all shared one `sent_at`."""
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)

    first = _pending_notification(user.id, "first")
    first.created_at = datetime.now(UTC) - timedelta(minutes=1)
    last = _pending_notification(user.id, "last")
    db_session.add_all([first, last])
    db_session.commit()
    await dispatcher.dispatch_pending(db_session)

    assert record_ack(db_session, user.id, AckAction.dismissed, 0).id == last.id


def test_record_ack_ignores_alert_channel(db_session, user):
    reminder = _pending_notification(user.id, "reminder")
    reminder.status = NotificationStatus.sent
    reminder.sent_at = datetime.now(UTC) - timedelta(seconds=30)
    alert = _pending_alert(user.id)
    alert.status = NotificationStatus.sent
    alert.sent_at = datetime.now(UTC)  # more recent, still awaiting `delivered`
    db_session.add_all([reminder, alert])
    db_session.commit()

    assert record_ack(db_session, user.id, AckAction.dismissed, 0).id == reminder.id
    db_session.refresh(alert)
    assert alert.status == NotificationStatus.sent


def test_record_delivered_drops_confirmation_for_row_requeued_concurrently(db_session, user, monkeypatch):
    """A requeue job (another thread) flips the row back to `pending` between the match and the
    write - the delivered must not land on a row that's about to be resent anyway."""
    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC)
    db_session.add(notification)
    db_session.commit()

    from app.notify import ack

    real_update = ack._update_if_still_sent

    def requeue_first(db, n, values, undelivered=False):
        db.query(Notification).filter(Notification.id == n.id).update(
            {Notification.status: NotificationStatus.pending}, synchronize_session=False
        )
        db.commit()
        return real_update(db, n, values, undelivered)

    monkeypatch.setattr(ack, "_update_if_still_sent", requeue_first)

    assert record_delivered(db_session, user.id) is None
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.pending
    assert notification.delivered_at is None


@pytest.mark.asyncio
async def test_resend_now_resends_sent_but_undelivered_immediately(db_session, user, monkeypatch):
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)
    monkeypatch.setattr(dispatcher.settings, "delivery_timeout_seconds", 9999)  # would not be due yet

    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=1)
    notification.send_attempts = 1
    db_session.add(notification)
    db_session.commit()

    resent = await dispatcher.resend_now(db_session, user.id)

    assert resent == 1
    assert fake.sent[0][0] == user.id
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.sent
    assert notification.send_attempts == 2


@pytest.mark.asyncio
async def test_resend_now_ignores_already_delivered(db_session, user, monkeypatch):
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)

    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=1)
    notification.delivered_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(notification)
    db_session.commit()

    assert await dispatcher.resend_now(db_session, user.id) == 0
    assert fake.sent == []


@pytest.mark.asyncio
async def test_resend_now_revives_failed_notification_with_fresh_attempt_budget(db_session, user, monkeypatch):
    """The exact case `watch_ready` exists for: the watch was away long enough that the server
    gave up (`failed`) before it came back. Reconnecting must still fire the reminder."""
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)
    monkeypatch.setattr(dispatcher.settings, "max_send_attempts", 2)

    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.failed
    notification.send_attempts = 2
    notification.error = "No connected device after max_send_attempts"
    db_session.add(notification)
    db_session.commit()

    resent = await dispatcher.resend_now(db_session, user.id)

    assert resent == 1
    assert fake.sent[0][0] == user.id
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.sent
    assert notification.send_attempts == 1  # fresh budget, not resumed from the old exhausted count
    assert notification.error is None


@pytest.mark.asyncio
async def test_resend_now_only_touches_the_given_user(db_session, user, monkeypatch):
    other = User(email="grace@example.com", timezone="UTC")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    fake = FakeConnectionManager(connected_users={user.id, other.id})
    monkeypatch.setattr(dispatcher, "manager", fake)

    mine = _pending_notification(user.id, dedupe_key="mine")
    mine.status = NotificationStatus.sent
    mine.sent_at = datetime.now(UTC) - timedelta(seconds=1)
    theirs = _pending_notification(other.id, dedupe_key="theirs")
    theirs.status = NotificationStatus.sent
    theirs.sent_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add_all([mine, theirs])
    db_session.commit()

    assert await dispatcher.resend_now(db_session, user.id) == 1
    db_session.refresh(theirs)
    assert theirs.status == NotificationStatus.sent  # untouched - not this user, so resend_now leaves it alone


def test_requeue_unacked_resends_after_timeout(db_session, user, monkeypatch):
    monkeypatch.setattr(dispatcher.settings, "ack_timeout_seconds", 60)
    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=120)
    notification.delivered_at = datetime.now(UTC) - timedelta(seconds=115)
    notification.send_attempts = 1
    db_session.add(notification)
    db_session.commit()

    requeued = dispatcher.requeue_unacked(db_session)

    assert requeued == 1
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.pending
    assert notification.delivered_at is None  # a resend needs reconfirming, same as a first send


def test_requeue_unacked_leaves_recently_sent_alone(db_session, user, monkeypatch):
    monkeypatch.setattr(dispatcher.settings, "ack_timeout_seconds", 300)
    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=5)
    notification.delivered_at = datetime.now(UTC) - timedelta(seconds=5)
    db_session.add(notification)
    db_session.commit()

    assert dispatcher.requeue_unacked(db_session) == 0


def test_requeue_unacked_ignores_undelivered(db_session, user, monkeypatch):
    """requeue_unacked is the post-delivery nag loop - anything never delivered is
    requeue_undelivered's job, resending it here too would just double-send."""
    monkeypatch.setattr(dispatcher.settings, "ack_timeout_seconds", 60)
    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=120)
    db_session.add(notification)
    db_session.commit()

    assert dispatcher.requeue_unacked(db_session) == 0


def test_requeue_undelivered_resends_after_timeout(db_session, user, monkeypatch):
    monkeypatch.setattr(dispatcher.settings, "delivery_timeout_seconds", 60)
    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=120)
    notification.send_attempts = 1
    db_session.add(notification)
    db_session.commit()

    requeued = dispatcher.requeue_undelivered(db_session)

    assert requeued == 1
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.pending


def test_requeue_undelivered_leaves_recently_sent_alone(db_session, user, monkeypatch):
    monkeypatch.setattr(dispatcher.settings, "delivery_timeout_seconds", 60)
    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=5)
    db_session.add(notification)
    db_session.commit()

    assert dispatcher.requeue_undelivered(db_session) == 0


def test_requeue_undelivered_ignores_already_delivered(db_session, user, monkeypatch):
    monkeypatch.setattr(dispatcher.settings, "delivery_timeout_seconds", 60)
    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=120)
    notification.delivered_at = datetime.now(UTC) - timedelta(seconds=110)
    db_session.add(notification)
    db_session.commit()

    assert dispatcher.requeue_undelivered(db_session) == 0


def test_requeue_undelivered_fails_after_max_attempts(db_session, user, monkeypatch):
    monkeypatch.setattr(dispatcher.settings, "delivery_timeout_seconds", 60)
    monkeypatch.setattr(dispatcher.settings, "max_send_attempts", 1)
    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=120)
    notification.send_attempts = 1
    db_session.add(notification)
    db_session.commit()

    dispatcher.requeue_undelivered(db_session)

    db_session.refresh(notification)
    assert notification.status == NotificationStatus.failed
    assert notification.error == "No delivery confirmation received after max_send_attempts"


def test_record_ack_updates_most_recently_sent_notification(db_session, user):
    older = _pending_notification(user.id, dedupe_key="old")
    older.status = NotificationStatus.sent
    older.sent_at = datetime.now(UTC) - timedelta(minutes=10)
    newer = _pending_notification(user.id, dedupe_key="new")
    newer.status = NotificationStatus.sent
    newer.sent_at = datetime.now(UTC)
    db_session.add_all([older, newer])
    db_session.commit()

    acked = record_ack(db_session, user.id, AckAction.snoozed, 15)

    assert acked.id == newer.id
    assert acked.status == NotificationStatus.acked
    assert acked.ack_action == AckAction.snoozed
    assert acked.ack_snoozed_minutes == 15
    assert acked.acked_at is not None


def test_record_ack_with_no_sent_notification_returns_none(db_session, user):
    assert record_ack(db_session, user.id, AckAction.dismissed, 0) is None


def test_record_delivered_updates_most_recently_sent_undelivered_notification(db_session, user):
    older = _pending_notification(user.id, dedupe_key="old")
    older.status = NotificationStatus.sent
    older.sent_at = datetime.now(UTC) - timedelta(minutes=10)
    newer = _pending_notification(user.id, dedupe_key="new")
    newer.status = NotificationStatus.sent
    newer.sent_at = datetime.now(UTC)
    db_session.add_all([older, newer])
    db_session.commit()

    delivered = record_delivered(db_session, user.id)

    assert delivered.id == newer.id
    assert delivered.delivered_at is not None
    assert delivered.status == NotificationStatus.sent  # delivery != wearer acted on it


def test_record_delivered_skips_already_delivered_notification(db_session, user):
    already_delivered = _pending_notification(user.id, dedupe_key="old")
    already_delivered.status = NotificationStatus.sent
    already_delivered.sent_at = datetime.now(UTC) - timedelta(minutes=10)
    already_delivered.delivered_at = datetime.now(UTC) - timedelta(minutes=9)
    undelivered = _pending_notification(user.id, dedupe_key="new")
    undelivered.status = NotificationStatus.sent
    undelivered.sent_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.add_all([already_delivered, undelivered])
    db_session.commit()

    delivered = record_delivered(db_session, user.id)

    assert delivered.id == undelivered.id


def test_record_delivered_with_no_sent_notification_returns_none(db_session, user):
    assert record_delivered(db_session, user.id) is None


@pytest.mark.asyncio
async def test_resend_now_does_not_revive_ignored_reminder(db_session, user, monkeypatch):
    """Failed after being delivered and nagged max_send_attempts times - the wearer ignored it,
    and reconnecting doesn't change that."""
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)

    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.failed
    notification.delivered_at = datetime.now(UTC) - timedelta(minutes=30)
    notification.error = "No ack received after max_send_attempts"
    db_session.add(notification)
    db_session.commit()

    assert await dispatcher.resend_now(db_session, user.id) == 0
    assert fake.sent == []


@pytest.mark.asyncio
async def test_resend_now_does_not_revive_expired(db_session, user, monkeypatch):
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)

    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.failed
    notification.error = "No delivery confirmation received after max_send_attempts"
    notification.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.add(notification)
    db_session.commit()

    assert await dispatcher.resend_now(db_session, user.id) == 0
    assert fake.sent == []


@pytest.mark.asyncio
async def test_dispatch_pending_expires_instead_of_sending(db_session, user, monkeypatch):
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)

    notification = _pending_notification(user.id)
    notification.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(notification)
    db_session.commit()

    assert await dispatcher.dispatch_pending(db_session) == 0
    assert fake.sent == []
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.failed
    assert notification.error == "Expired"


def test_notifications_get_a_default_expiry(db_session, user):
    notification = _pending_notification(user.id)
    db_session.add(notification)
    db_session.commit()

    assert notification.expires_at is not None
    assert notification.expires_at > datetime.now(UTC) + timedelta(hours=23)


def _pending_nudge(user_id: str, dedupe_key: str = "n1") -> Notification:
    notification = _pending_notification(user_id, dedupe_key)
    notification.kind = ReminderKind.generic
    notification.body = "Water the plants"
    return notification


def _connected(monkeypatch, user) -> FakeConnectionManager:
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)
    return fake


@pytest.mark.asyncio
async def test_a_nudge_waits_while_a_medication_reminder_is_unacked(db_session, user, monkeypatch):
    fake = _connected(monkeypatch, user)
    medication = _pending_notification(user.id)
    db_session.add(medication)
    db_session.commit()
    await dispatcher.dispatch_pending(db_session)

    nudge = _pending_nudge(user.id)
    db_session.add(nudge)
    db_session.commit()
    await dispatcher.dispatch_pending(db_session)

    db_session.refresh(nudge)
    assert nudge.status == NotificationStatus.pending
    assert nudge.send_attempts == 0
    assert [payload["body"] for _, payload in fake.sent] == ["Take meds"]


@pytest.mark.asyncio
async def test_the_held_nudge_goes_out_once_the_medication_is_acked(db_session, user, monkeypatch):
    fake = _connected(monkeypatch, user)
    db_session.add_all([_pending_notification(user.id), _pending_nudge(user.id)])
    db_session.commit()
    await dispatcher.dispatch_pending(db_session)

    acked = record_ack(db_session, user.id, AckAction.dismissed, 0)
    await dispatcher.dispatch_pending(db_session)

    assert acked.body == "Take meds"
    assert [payload["body"] for _, payload in fake.sent] == ["Take meds", "Water the plants"]


@pytest.mark.asyncio
async def test_an_ack_is_credited_to_the_medication_not_a_later_nudge(db_session, user, monkeypatch):
    _connected(monkeypatch, user)
    medication = _pending_notification(user.id)
    db_session.add(medication)
    db_session.commit()
    await dispatcher.dispatch_pending(db_session)
    db_session.add(_pending_nudge(user.id))
    db_session.commit()
    await dispatcher.dispatch_pending(db_session)

    record_ack(db_session, user.id, AckAction.dismissed, 0)

    db_session.refresh(medication)
    assert medication.status == NotificationStatus.acked


@pytest.mark.asyncio
async def test_a_newer_medication_goes_before_an_older_nudge(db_session, user, monkeypatch):
    fake = _connected(monkeypatch, user)
    nudge = _pending_nudge(user.id)
    nudge.created_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.add_all([nudge, _pending_notification(user.id)])
    db_session.commit()

    await dispatcher.dispatch_pending(db_session)

    assert [payload["body"] for _, payload in fake.sent] == ["Take meds"]


@pytest.mark.asyncio
async def test_an_alert_is_not_held_back_by_medication(db_session, user, monkeypatch):
    fake = _connected(monkeypatch, user)
    db_session.add_all([_pending_notification(user.id), _pending_alert(user.id)])
    db_session.commit()

    await dispatcher.dispatch_pending(db_session)

    assert len(fake.sent) == 2


@pytest.mark.asyncio
async def test_a_given_up_medication_stops_holding_nudges(db_session, user, monkeypatch):
    fake = _connected(monkeypatch, user)
    medication = _pending_notification(user.id)
    medication.status = NotificationStatus.failed
    db_session.add_all([medication, _pending_nudge(user.id)])
    db_session.commit()

    await dispatcher.dispatch_pending(db_session)

    assert [payload["body"] for _, payload in fake.sent] == ["Water the plants"]


@pytest.mark.asyncio
async def test_one_users_medication_does_not_hold_another_users_nudge(db_session, user, monkeypatch):
    other = User(email="other@example.com", timezone="UTC")
    db_session.add(other)
    db_session.commit()
    fake = FakeConnectionManager(connected_users={user.id, other.id})
    monkeypatch.setattr(dispatcher, "manager", fake)
    db_session.add_all([_pending_notification(user.id), _pending_nudge(other.id)])
    db_session.commit()

    await dispatcher.dispatch_pending(db_session)

    assert len(fake.sent) == 2
