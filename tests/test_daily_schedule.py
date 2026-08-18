from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import DailySchedule, Notification, NotificationStatus
from app.scheduler.daily import run_daily_schedule_tick


def _utc_for_local(local_naive: datetime, tz: str) -> datetime:
    return local_naive.replace(tzinfo=ZoneInfo(tz)).astimezone(ZoneInfo("UTC"))


def test_enqueues_todays_occurrence_when_still_upcoming(db_session, user):
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
    assert notification.scheduled_for == now


def test_pushes_ahead_to_next_occurrence_once_todays_has_passed(db_session, user):
    """The whole point of pushing ahead of fire time: a tick running *after* today's time_of_day
    already enqueues *tomorrow's* occurrence (with its own future scheduled_for), rather than
    waiting for tomorrow's tick to notice."""
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds")
    db_session.add(schedule)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 9, 1), user.timezone)
    created = run_daily_schedule_tick(db_session, now=now)

    assert created == 1
    notification = db_session.query(Notification).one()
    expected = _utc_for_local(datetime(2024, 1, 4, 9, 0), user.timezone)
    assert notification.scheduled_for == expected


def test_respects_weekday_mask_by_rolling_to_the_next_enabled_day(db_session, user):
    # Monday-only mask (bit 0); 2024-01-03 is a Wednesday, so the next enabled day is 2024-01-08.
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds", weekdays_mask=0b0000001)
    db_session.add(schedule)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 9, 0), user.timezone)
    created = run_daily_schedule_tick(db_session, now=now)

    assert created == 1
    notification = db_session.query(Notification).one()
    expected = _utc_for_local(datetime(2024, 1, 8, 9, 0), user.timezone)
    assert notification.scheduled_for == expected


def test_disabled_schedule_is_skipped(db_session, user):
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds", enabled=False)
    db_session.add(schedule)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 9, 0), user.timezone)
    assert run_daily_schedule_tick(db_session, now=now) == 0


def test_dedupes_the_same_occurrence_across_ticks(db_session, user):
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds")
    db_session.add(schedule)
    db_session.commit()

    now = _utc_for_local(datetime(2024, 1, 3, 9, 0), user.timezone)
    run_daily_schedule_tick(db_session, now=now)
    created_again = run_daily_schedule_tick(db_session, now=now)

    assert created_again == 0
    assert db_session.query(Notification).count() == 1


def test_enqueues_the_following_occurrence_once_the_current_one_has_passed(db_session, user):
    """After the first occurrence's date has passed, the next tick enqueues the day after that -
    always exactly one future occurrence known ahead of time, per the "push as soon as it's
    known" design."""
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds")
    db_session.add(schedule)
    db_session.commit()

    first_tick = _utc_for_local(datetime(2024, 1, 3, 9, 0), user.timezone)
    run_daily_schedule_tick(db_session, now=first_tick)

    second_tick = _utc_for_local(datetime(2024, 1, 4, 9, 0), user.timezone)
    created = run_daily_schedule_tick(db_session, now=second_tick)

    assert created == 1
    assert db_session.query(Notification).count() == 2
