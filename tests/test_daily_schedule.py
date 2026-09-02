from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import DailySchedule, Notification, NotificationStatus, User
from app.scheduler.daily import run_daily_schedule_tick


def _utc_for_local(local_naive: datetime, tz: str) -> datetime:
    return local_naive.replace(tzinfo=ZoneInfo(tz)).astimezone(ZoneInfo("UTC"))


def test_fires_when_local_time_matches(db_session, user):
    # user.timezone is Europe/Paris; schedule fires at 09:00 local on a Wednesday.
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds")
    db_session.add(schedule)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 9, 0), user.timezone)  # 2024-01-03 is a Wednesday
    created = run_daily_schedule_tick(db_session, now=now)

    assert created == 1
    notification = db_session.query(Notification).one()
    assert notification.body == "Take meds"
    assert notification.status == NotificationStatus.pending


def test_does_not_fire_at_wrong_time(db_session, user):
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds")
    db_session.add(schedule)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 9, 1), user.timezone)
    assert run_daily_schedule_tick(db_session, now=now) == 0


def test_respects_weekday_mask(db_session, user):
    # Monday-only mask (bit 0), but 2024-01-03 is a Wednesday.
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds", weekdays_mask=0b0000001)
    db_session.add(schedule)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 9, 0), user.timezone)
    assert run_daily_schedule_tick(db_session, now=now) == 0


def test_disabled_schedule_is_skipped(db_session, user):
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds", enabled=False)
    db_session.add(schedule)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 9, 0), user.timezone)
    assert run_daily_schedule_tick(db_session, now=now) == 0


def test_dedupes_within_the_same_day(db_session, user):
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds")
    db_session.add(schedule)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 9, 0), user.timezone)
    run_daily_schedule_tick(db_session, now=now)
    created_again = run_daily_schedule_tick(db_session, now=now)

    assert created_again == 0
    assert db_session.query(Notification).count() == 1


def test_bad_timezone_on_one_user_does_not_block_another(db_session, user):
    """A row with a timezone ZoneInfo can't load (e.g. from data predating the UserUpdate/
    UserCreate validation) must be skipped, not abort the tick before other users are checked."""
    broken = User(email="broken@example.com", timezone="Not/AZone")
    db_session.add(broken)
    db_session.flush()
    broken_schedule = DailySchedule(user_id=broken.id, time_of_day="09:00", message="Broken")
    db_session.add(broken_schedule)

    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds")
    db_session.add(schedule)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 9, 0), user.timezone)
    created = run_daily_schedule_tick(db_session, now=now)

    assert created == 1
    notification = db_session.query(Notification).one()
    assert notification.user_id == user.id
