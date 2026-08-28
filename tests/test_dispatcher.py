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
async def test_dispatch_pending_fails_after_max_attempts(db_session, user, monkeypatch):
    fake = FakeConnectionManager(connected_users=set())  # nobody connected
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
