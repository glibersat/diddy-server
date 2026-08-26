from datetime import datetime, UTC

import pytest

from app.models import Notification, NotificationStatus, ReminderKind, RuleType
from app.notify import dispatcher


class FakeConnectionManager:
    def __init__(self, connected_users: set[str]):
        self.connected_users = connected_users

    async def send_to_user(self, user_id: str, payload: dict) -> bool:
        return user_id in self.connected_users


def _pending_notification(user_id: str, dedupe_key: str = "d1") -> Notification:
    return Notification(
        user_id=user_id,
        rule_type=RuleType.daily_schedule,
        rule_id="rule-1",
        dedupe_key=dedupe_key,
        scheduled_for=datetime.now(UTC),
        title="Take your meds",
        body="It's 8am",
        kind=ReminderKind.medication,
        dismissible=False,
        snooze_minutes=[5, 15],
    )


@pytest.mark.asyncio
async def test_dispatch_pending_sends_signal_message_when_user_has_a_number(db_session, user, monkeypatch):
    user.signal_number = "+15551234567"
    db_session.commit()
    monkeypatch.setattr(dispatcher, "manager", FakeConnectionManager(connected_users=set()))
    sent = []

    async def fake_send(to_number, text):
        sent.append((to_number, text))
        return True

    monkeypatch.setattr(dispatcher, "send_signal_message", fake_send)

    notification = _pending_notification(user.id)
    db_session.add(notification)
    db_session.commit()

    await dispatcher.dispatch_pending(db_session)

    assert sent == [("+15551234567", "Take your meds\nIt's 8am")]
    db_session.refresh(notification)
    assert notification.signal_sent_at is not None


@pytest.mark.asyncio
async def test_dispatch_pending_skips_signal_when_user_has_no_number(db_session, user, monkeypatch):
    monkeypatch.setattr(dispatcher, "manager", FakeConnectionManager(connected_users=set()))
    called = False

    async def fake_send(to_number, text):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(dispatcher, "send_signal_message", fake_send)

    notification = _pending_notification(user.id)
    db_session.add(notification)
    db_session.commit()

    await dispatcher.dispatch_pending(db_session)

    assert called is False
    db_session.refresh(notification)
    assert notification.signal_sent_at is None


@pytest.mark.asyncio
async def test_dispatch_pending_does_not_resend_signal_on_watch_retry(db_session, user, monkeypatch):
    """A watch-trigger resend (requeue_undelivered/requeue_unacked flipping the row back to
    `pending`) must not re-text the wearer every time - signal_sent_at is a standalone guard."""
    user.signal_number = "+15551234567"
    db_session.commit()
    monkeypatch.setattr(dispatcher, "manager", FakeConnectionManager(connected_users={user.id}))
    send_count = 0

    async def fake_send(to_number, text):
        nonlocal send_count
        send_count += 1
        return True

    monkeypatch.setattr(dispatcher, "send_signal_message", fake_send)

    notification = _pending_notification(user.id)
    db_session.add(notification)
    db_session.commit()

    await dispatcher.dispatch_pending(db_session)
    assert send_count == 1

    # Simulate a watch-trigger resend: back to pending, Signal already tried.
    notification.status = NotificationStatus.pending
    db_session.commit()
    await dispatcher.dispatch_pending(db_session)

    assert send_count == 1


@pytest.mark.asyncio
async def test_dispatch_pending_tries_signal_even_if_watch_send_failed(db_session, user, monkeypatch):
    user.signal_number = "+15551234567"
    db_session.commit()
    monkeypatch.setattr(dispatcher, "manager", FakeConnectionManager(connected_users=set()))
    sent = []

    async def fake_send(to_number, text):
        sent.append(to_number)
        return True

    monkeypatch.setattr(dispatcher, "send_signal_message", fake_send)

    notification = _pending_notification(user.id)
    db_session.add(notification)
    db_session.commit()

    await dispatcher.dispatch_pending(db_session)

    assert sent == ["+15551234567"]
