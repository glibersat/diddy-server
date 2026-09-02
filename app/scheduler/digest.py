"""Criterion #3: a once-a-day summary of the day's appointments, sent at `User.digest_time`.

Reuses the same ICS expansion as app/scheduler/ics.py, but over the whole local day rather than
a lookahead window - and unlike daily.py/ics.py, sends nothing at all if there's nothing to show.
"""

import logging
from datetime import datetime, time, timedelta, UTC
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models import IcsSource, NotificationChannel, ReminderKind, RuleType, User
from app.notify.queue import enqueue_notification
from app.scheduler import ics

logger = logging.getLogger("diddy.scheduler.digest")

MAX_LISTED = 5  # keep the body short enough for the watch's screen


def _todays_appointments(db: Session, user: User, local_now: datetime) -> list[ics.Occurrence]:
    tz = local_now.tzinfo
    day_start = datetime.combine(local_now.date(), time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    occurrences: list[ics.Occurrence] = []
    sources = db.query(IcsSource).filter(IcsSource.user_id == user.id, IcsSource.enabled.is_(True)).all()
    for source in sources:
        try:
            ics_text = ics.fetch_ics_text(source.url_or_path)
        except Exception:
            continue  # source unreachable right now - don't let it block the rest of the digest
        occurrences.extend(ics.expand_occurrences(ics_text, day_start, day_end))
    occurrences.sort(key=lambda o: o.start)
    return occurrences


def _format_body(appointments: list[ics.Occurrence], tz: ZoneInfo) -> str:
    listed = [f"{a.start.astimezone(tz).strftime('%H:%M')} {a.summary}" for a in appointments[:MAX_LISTED]]
    remainder = len(appointments) - len(listed)
    if remainder > 0:
        listed.append(f"+{remainder} more")
    return f"{len(appointments)} today: " + ", ".join(listed)


def run_digest_tick(db: Session, now: datetime | None = None) -> int:
    """Check every user with digest_enabled against `now`; enqueue a digest Notification for
    those whose local time matches `digest_time` and who have at least one appointment today.

    Returns the number of notifications newly enqueued.
    """
    now = now or datetime.now(UTC)
    created = 0
    users = db.query(User).filter(User.digest_enabled.is_(True), User.digest_time.isnot(None)).all()
    for user in users:
        try:
            tz = ZoneInfo(user.timezone)
        except ZoneInfoNotFoundError:
            # Don't let one user's bad timezone abort the tick for everyone queried after them.
            logger.error("Skipping digest for user %s: invalid timezone %r", user.id, user.timezone)
            continue
        local_now = now.astimezone(tz)
        if local_now.strftime("%H:%M") != user.digest_time:
            continue

        appointments = _todays_appointments(db, user, local_now)
        if not appointments:
            continue

        dedupe_key = f"digest:{user.id}:{local_now.date().isoformat()}"
        notification = enqueue_notification(
            db,
            user.id,
            rule_type=RuleType.daily_digest,
            rule_id=user.id,
            dedupe_key=dedupe_key,
            title="Today's schedule",
            body=_format_body(appointments, tz),
            channel=NotificationChannel.alert,
            kind=ReminderKind.generic,
            dismissible=True,
            snooze_minutes=[],
        )
        if notification is not None:  # None means already enqueued this minute/day, e.g. after a restart
            created += 1
    return created
