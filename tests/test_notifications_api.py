from datetime import datetime, timedelta, UTC

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app import schemas
from app.models import Notification, NotificationChannel, NotificationStatus, ReminderKind, User
from app.notify import dispatcher
from app.routers.notifications import cancel_notification, create_notification
from tests.test_dispatcher import FakeConnectionManager, _pending_notification


def payload(**fields) -> schemas.NotificationCreate:
    return schemas.NotificationCreate(**{"dedupe_key": "note-1", "body": "Appeler le dentiste", **fields})


def queue(db_session, user, **fields) -> tuple[Notification, int]:
    response = Response(status_code=201)
    notification = create_notification(payload(**fields), response, user, db_session)
    return notification, response.status_code


def _connected(monkeypatch, user) -> FakeConnectionManager:
    fake = FakeConnectionManager(connected_users={user.id})
    monkeypatch.setattr(dispatcher, "manager", fake)
    return fake


def test_a_queued_notification_is_snoozable_by_default(db_session, user):
    notification, status = queue(db_session, user)

    assert status == 201
    assert notification.status == NotificationStatus.pending
    assert notification.snooze_minutes == [5, 15]


def test_a_retry_with_the_same_key_returns_the_first_notification(db_session, user):
    first, _ = queue(db_session, user)
    second, status = queue(db_session, user)

    assert status == 200
    assert second.id == first.id
    assert db_session.query(Notification).count() == 1


def test_two_users_can_use_the_same_key(db_session, user):
    other = User(email="other@example.com", timezone="UTC")
    db_session.add(other)
    db_session.commit()

    queue(db_session, user)
    _, status = queue(db_session, other)

    assert status == 201
    assert db_session.query(Notification).count() == 2


def test_medication_is_refused():
    with pytest.raises(ValidationError, match="medication"):
        payload(kind=ReminderKind.medication)


@pytest.mark.parametrize(
    "fields",
    [
        {"body": "é" * 31},
        {"title": "x" * 61},
        {"body": "x" * 101, "channel": NotificationChannel.alert},
        {"dismissible": False, "snooze_minutes": []},
        {"snooze_minutes": [0]},
        {"scheduled_for": datetime(2026, 11, 12, 9, 0)},
    ],
)
def test_what_the_watch_cannot_show_is_refused(fields):
    with pytest.raises(ValidationError):
        payload(**fields)


def test_an_alert_can_use_its_longer_limit():
    assert payload(body="x" * 100, channel=NotificationChannel.alert)


@pytest.mark.asyncio
async def test_a_later_reminder_waits_until_it_is_due(db_session, user, monkeypatch):
    fake = _connected(monkeypatch, user)
    notification, _ = queue(db_session, user, scheduled_for=datetime.now(UTC) + timedelta(days=3))

    assert await dispatcher.dispatch_pending(db_session) == 0
    assert fake.sent == []

    notification.scheduled_for = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    assert await dispatcher.dispatch_pending(db_session) == 1


@pytest.mark.asyncio
async def test_a_reminder_days_away_does_not_expire_first(db_session, user, monkeypatch):
    _connected(monkeypatch, user)
    due = datetime.now(UTC) + timedelta(days=3)
    notification, _ = queue(db_session, user, scheduled_for=due)

    await dispatcher.dispatch_pending(db_session)

    db_session.refresh(notification)
    assert notification.status == NotificationStatus.pending
    assert notification.expires_at.replace(tzinfo=UTC) > due


@pytest.mark.asyncio
async def test_a_future_medication_reminder_holds_nothing_yet(db_session, user, monkeypatch):
    fake = _connected(monkeypatch, user)
    medication = _pending_notification(user.id)
    medication.scheduled_for = datetime.now(UTC) + timedelta(hours=2)
    db_session.add(medication)
    db_session.commit()
    queue(db_session, user)

    await dispatcher.dispatch_pending(db_session)

    assert [sent["body"] for _, sent in fake.sent] == ["Appeler le dentiste"]


def test_a_waiting_reminder_can_be_cancelled(db_session, user):
    notification, _ = queue(db_session, user, scheduled_for=datetime.now(UTC) + timedelta(days=1))

    cancel_notification(notification.id, user, db_session)

    assert db_session.query(Notification).count() == 0


def test_a_reminder_that_went_out_cannot_be_cancelled(db_session, user):
    notification, _ = queue(db_session, user)
    notification.status = NotificationStatus.sent
    notification.sent_at = datetime.now(UTC)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        cancel_notification(notification.id, user, db_session)

    assert error.value.status_code == 409


def test_another_users_reminder_cannot_be_cancelled(db_session, user):
    other = User(email="other@example.com", timezone="UTC")
    db_session.add(other)
    db_session.commit()
    notification, _ = queue(db_session, user)

    with pytest.raises(HTTPException) as error:
        cancel_notification(notification.id, other, db_session)

    assert error.value.status_code == 404
    assert db_session.query(Notification).count() == 1
