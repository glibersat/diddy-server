"""Predicts the next reminder that will fire, for the frontend's "what's coming up" panel.

This is distinct from `Notification` rows, which only get created once a reminder actually
becomes due (see app/scheduler/daily.py and app/scheduler/ics.py) - there's nothing in the
database yet to query for "what's next", so this walks the enabled rules directly instead.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, UTC
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import DailySchedule, IcsSource, ReminderKind, RuleType, User
from app.scheduler import ics

LOOKAHEAD_DAYS = 7


@dataclass
class NextReminder:
    rule_type: RuleType
    title: str
    body: str
    kind: ReminderKind
    scheduled_for: datetime


def _next_daily_occurrence(schedule: DailySchedule, user: User, now: datetime) -> datetime | None:
    tz = ZoneInfo(user.timezone)
    local_now = now.astimezone(tz)
    hour, minute = (int(part) for part in schedule.time_of_day.split(":"))
    for days_ahead in range(LOOKAHEAD_DAYS + 1):
        candidate_date = (local_now + timedelta(days=days_ahead)).date()
        candidate = datetime.combine(candidate_date, time(hour, minute), tzinfo=tz)
        if candidate <= local_now:
            continue
        if schedule.weekdays_mask & (1 << candidate.weekday()):
            return candidate.astimezone(UTC)
    return None  # weekdays_mask == 0 - schedule can never actually fire


def _next_daily_reminders(db: Session, user_id: str, now: datetime) -> list[NextReminder]:
    schedules = (
        db.query(DailySchedule).filter(DailySchedule.user_id == user_id, DailySchedule.enabled.is_(True)).all()
    )
    reminders = []
    for schedule in schedules:
        fires_at = _next_daily_occurrence(schedule, schedule.user, now)
        if fires_at is None:
            continue
        reminders.append(
            NextReminder(
                rule_type=RuleType.daily_schedule,
                title="Reminder",
                body=schedule.message,
                kind=schedule.kind,
                scheduled_for=fires_at,
            )
        )
    return reminders


def _next_ics_reminders(db: Session, user_id: str, now: datetime) -> list[NextReminder]:
    sources = db.query(IcsSource).filter(IcsSource.user_id == user_id, IcsSource.enabled.is_(True)).all()
    window_end = now + timedelta(days=LOOKAHEAD_DAYS)
    reminders = []
    for source in sources:
        try:
            ics_text = ics.fetch_ics_text(source.url_or_path)
        except Exception:
            continue  # source unreachable right now - not this endpoint's job to surface that
        for occurrence in ics.expand_occurrences(ics_text, now, window_end):
            for offset in source.offsets_minutes:
                trigger = occurrence.start - timedelta(minutes=offset)
                if trigger <= now:
                    continue  # already due (or would be caught by the next dispatch tick), not "next"
                reminders.append(
                    NextReminder(
                        rule_type=RuleType.ics_reminder,
                        title=f"In {offset} min: {occurrence.summary}",
                        body=f"{occurrence.summary} starts at {occurrence.start.strftime('%H:%M')}",
                        kind=source.kind,
                        scheduled_for=trigger,
                    )
                )
    return reminders


def next_reminder(db: Session, user_id: str, now: datetime | None = None) -> NextReminder | None:
    """The single soonest reminder still ahead of `now`, across every enabled rule for this user -
    what the frontend shows as "next up" after the currently snoozed/active notifications.
    """
    now = now or datetime.now(UTC)
    candidates = _next_daily_reminders(db, user_id, now) + _next_ics_reminders(db, user_id, now)
    if not candidates:
        return None
    return min(candidates, key=lambda r: r.scheduled_for)
