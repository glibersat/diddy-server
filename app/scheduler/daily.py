"""Criterion #1: fixed daily schedules (e.g. "take meds at 9am")."""

import logging
from datetime import datetime, UTC
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models import DailySchedule, RuleType
from app.notify.queue import enqueue_notification

logger = logging.getLogger("diddy.scheduler.daily")


def _weekday_bit(dt: datetime) -> int:
    """dt.weekday(): Monday=0 ... Sunday=6, matching our mask's bit order."""
    return 1 << dt.weekday()


def run_daily_schedule_tick(db: Session, now: datetime | None = None) -> int:
    """Check every enabled DailySchedule against `now`; enqueue a Notification for matches.

    Returns the number of notifications newly enqueued.
    """
    now = now or datetime.now(UTC)
    created = 0
    schedules = db.query(DailySchedule).filter(DailySchedule.enabled.is_(True)).all()
    for schedule in schedules:
        user = schedule.user
        try:
            tz = ZoneInfo(user.timezone)
        except ZoneInfoNotFoundError:
            # Don't let one user's bad timezone abort the tick for everyone queried after them.
            logger.error("Skipping schedule %s: invalid timezone %r for user %s", schedule.id, user.timezone, user.id)
            continue
        local_now = now.astimezone(tz)
        if local_now.strftime("%H:%M") != schedule.time_of_day:
            continue
        if not (schedule.weekdays_mask & _weekday_bit(local_now)):
            continue

        dedupe_key = f"daily:{schedule.id}:{local_now.date().isoformat()}"
        notification = enqueue_notification(
            db,
            user.id,
            rule_type=RuleType.daily_schedule,
            rule_id=schedule.id,
            dedupe_key=dedupe_key,
            title="Reminder",
            body=schedule.message,
            kind=schedule.kind,
            dismissible=schedule.dismissible,
            snooze_minutes=schedule.snooze_minutes,
        )
        if notification is not None:  # None means already enqueued this minute/day, e.g. after a restart
            created += 1
    return created
