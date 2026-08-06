from datetime import datetime, timedelta, UTC

import pytest

from app.models import AckAction, Notification, NotificationStatus, ReminderKind, RuleType
from app.notify import dispatcher
from app.notify.ack import record_ack


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


def test_requeue_unacked_resends_after_timeout(db_session, user, monkeypatch):
    monkeypatch.setattr(dispatcher.settings, "ack_timeout_seconds", 60)
    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=120)
    notification.send_attempts = 1
    db_session.add(notification)
    db_session.commit()

    requeued = dispatcher.requeue_unacked(db_session)

    assert requeued == 1
    db_session.refresh(notification)
    assert notification.status == NotificationStatus.pending


def test_requeue_unacked_leaves_recently_sent_alone(db_session, user, monkeypatch):
    monkeypatch.setattr(dispatcher.settings, "ack_timeout_seconds", 300)
    notification = _pending_notification(user.id)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC) - timedelta(seconds=5)
    db_session.add(notification)
    db_session.commit()

    assert dispatcher.requeue_unacked(db_session) == 0


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
