"""Criterion #1: fixed daily schedules (e.g. "take meds at 9am")."""

from datetime import date, datetime, time, timedelta, UTC
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import DailySchedule, Notification, RuleType


def _weekday_bit(d: date) -> int:
    """date.weekday(): Monday=0 ... Sunday=6, matching our mask's bit order."""
    return 1 << d.weekday()


def _next_occurrence(schedule: DailySchedule, local_now: datetime) -> datetime:
    """The next local datetime >= `local_now` at which `schedule` is due - today if
    `time_of_day` hasn't passed yet and today's weekday is enabled, otherwise the soonest later
    enabled weekday. Pushed ahead of the actual tick that would have matched it (see
    run_daily_schedule_tick) so the watch can be told about it well before fire time, not just at
    the exact minute.
    """
    hour, minute = (int(part) for part in schedule.time_of_day.split(":"))
    time_of_day = time(hour, minute)

    candidate_date = local_now.date()
    for _ in range(8):  # at most a full week plus the starting day
        if schedule.weekdays_mask & _weekday_bit(candidate_date):
            candidate = datetime.combine(candidate_date, time_of_day, tzinfo=local_now.tzinfo)
            if candidate >= local_now:
                return candidate
        candidate_date += timedelta(days=1)
    raise ValueError(f"DailySchedule {schedule.id} has an empty weekdays_mask")


def run_daily_schedule_tick(db: Session, now: datetime | None = None) -> int:
    """Ensures every enabled DailySchedule has its next occurrence enqueued as a `pending`
    Notification, with `scheduled_for` set to that future fire time - not just at the exact
    matching minute like before. `dedupe_key` (keyed by occurrence date) makes this idempotent
    across ticks: once an occurrence is enqueued, re-running this only creates a *new* row once
    that occurrence's date has passed and the next one rolls into view.

    Returns the number of notifications newly enqueued.
    """
    now = now or datetime.now(UTC)
    created = 0
    schedules = db.query(DailySchedule).filter(DailySchedule.enabled.is_(True)).all()
    for schedule in schedules:
        user = schedule.user
        local_now = now.astimezone(ZoneInfo(user.timezone))
        try:
            occurrence = _next_occurrence(schedule, local_now)
        except ValueError:
            continue  # no weekday enabled - nothing to schedule

        dedupe_key = f"daily:{schedule.id}:{occurrence.date().isoformat()}"
        notification = Notification(
            user_id=user.id,
            rule_type=RuleType.daily_schedule,
            rule_id=schedule.id,
            dedupe_key=dedupe_key,
            scheduled_for=occurrence.astimezone(UTC),
            title="Reminder",
            body=schedule.message,
            kind=schedule.kind,
            dismissible=schedule.dismissible,
            snooze_minutes=schedule.snooze_minutes,
        )
        db.add(notification)
        try:
            db.commit()
            created += 1
        except IntegrityError:
            db.rollback()  # this occurrence is already enqueued
    return created
