from datetime import datetime, UTC
from pathlib import Path
from zoneinfo import ZoneInfo

from app.models import IcsSource, Notification, User
from app.scheduler.digest import run_digest_tick

FIXTURE = Path(__file__).parent / "fixtures" / "sample.ics"


def _utc_for_local(local_naive: datetime, tz: str) -> datetime:
    return local_naive.replace(tzinfo=ZoneInfo(tz)).astimezone(ZoneInfo("UTC"))


def test_sends_digest_when_appointments_exist(db_session, user, monkeypatch):
    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", lambda url_or_path: FIXTURE.read_text())
    user.digest_enabled = True
    user.digest_time = "07:00"
    source = IcsSource(user_id=user.id, url_or_path="https://example.com/calendar.ics")
    db_session.add(source)
    db_session.commit()

    # user.timezone is Europe/Paris; sample.ics has events on 2024-01-03 (UTC).
    now = _utc_for_local(datetime(2024, 1, 3, 7, 0), user.timezone)
    created = run_digest_tick(db_session, now=now)

    assert created == 1
    notification = db_session.query(Notification).one()
    assert "Dentist appointment" in notification.body
    assert notification.dismissible is True


def test_no_notification_when_nothing_to_show(db_session, user):
    user.digest_enabled = True
    user.digest_time = "07:00"
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 7, 0), user.timezone)
    assert run_digest_tick(db_session, now=now) == 0
    assert db_session.query(Notification).count() == 0


def test_does_not_fire_at_wrong_time(db_session, user, monkeypatch):
    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", lambda url_or_path: FIXTURE.read_text())
    user.digest_enabled = True
    user.digest_time = "07:00"
    source = IcsSource(user_id=user.id, url_or_path="https://example.com/calendar.ics")
    db_session.add(source)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 7, 1), user.timezone)
    assert run_digest_tick(db_session, now=now) == 0


def test_disabled_user_is_skipped(db_session, user, monkeypatch):
    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", lambda url_or_path: FIXTURE.read_text())
    user.digest_enabled = False
    user.digest_time = "07:00"
    source = IcsSource(user_id=user.id, url_or_path="https://example.com/calendar.ics")
    db_session.add(source)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 7, 0), user.timezone)
    assert run_digest_tick(db_session, now=now) == 0


def test_bad_timezone_on_one_user_does_not_block_another(db_session, user, monkeypatch):
    """A row with a timezone ZoneInfo can't load (e.g. from data predating the UserUpdate/
    UserCreate validation) must be skipped, not abort the tick before other users are checked."""
    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", lambda url_or_path: FIXTURE.read_text())

    broken = User(email="broken@example.com", timezone="Not/AZone", digest_enabled=True, digest_time="07:00")
    db_session.add(broken)
    user.digest_enabled = True
    user.digest_time = "07:00"
    source = IcsSource(user_id=user.id, url_or_path="https://example.com/calendar.ics")
    db_session.add(source)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 7, 0), user.timezone)
    created = run_digest_tick(db_session, now=now)

    assert created == 1
    notification = db_session.query(Notification).one()
    assert notification.user_id == user.id


def test_dedupes_within_the_same_day(db_session, user, monkeypatch):
    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", lambda url_or_path: FIXTURE.read_text())
    user.digest_enabled = True
    user.digest_time = "07:00"
    source = IcsSource(user_id=user.id, url_or_path="https://example.com/calendar.ics")
    db_session.add(source)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 7, 0), user.timezone)
    run_digest_tick(db_session, now=now)
    created_again = run_digest_tick(db_session, now=now)

    assert created_again == 0
    assert db_session.query(Notification).count() == 1
