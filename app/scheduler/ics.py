"""Criterion #2: reminders N minutes before events in a personal ICS export."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, UTC

import httpx
from dateutil.rrule import rrulestr
from icalendar import Calendar
from sqlalchemy.orm import Session

from app.models import IcsSource, NotificationChannel, RuleType
from app.notify.queue import enqueue_notification

LOOKAHEAD_BUFFER_MINUTES = 60  # extra margin past the largest offset, to tolerate slow/late ticks


@dataclass
class Occurrence:
    uid: str
    summary: str
    start: datetime


def fetch_ics_text(url_or_path: str) -> str:
    """Despite the name, only remote http(s) URLs are supported - see
    app/schemas.py::_validate_ics_url. A local-file fallback used to live here, but it let a
    self-registered user make the server read arbitrary files off its own disk."""
    if not (url_or_path.startswith("http://") or url_or_path.startswith("https://")):
        raise ValueError(f"Unsupported ICS source (must be http:// or https://): {url_or_path!r}")
    response = httpx.get(url_or_path, timeout=10, follow_redirects=True)
    response.raise_for_status()
    return response.text


def _as_datetime(value: date | datetime) -> datetime | None:
    """ICS all-day events (date, no time) can't support a "minutes before" offset; skip them."""
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def expand_occurrences(ics_text: str, window_start: datetime, window_end: datetime) -> list[Occurrence]:
    calendar = Calendar.from_ical(ics_text)
    occurrences: list[Occurrence] = []
    for component in calendar.walk("VEVENT"):
        uid = str(component.get("UID"))
        summary = str(component.get("SUMMARY", "Event"))
        dtstart = _as_datetime(component.get("DTSTART").dt)
        if dtstart is None:
            continue

        rrule = component.get("RRULE")
        if rrule is None:
            if window_start <= dtstart <= window_end:
                occurrences.append(Occurrence(uid, summary, dtstart))
            continue

        rule = rrulestr(rrule.to_ical().decode(), dtstart=dtstart)
        for start in rule.between(window_start, window_end, inc=True):
            occurrences.append(Occurrence(uid, summary, start))
    return occurrences


def compute_due(
    occurrences: list[Occurrence], offsets_minutes: list[int], now: datetime
) -> list[tuple[Occurrence, int]]:
    """An occurrence+offset is "due" once its trigger time has passed but the event hasn't started."""
    due = []
    for occurrence in occurrences:
        for offset in offsets_minutes:
            trigger = occurrence.start - timedelta(minutes=offset)
            if trigger <= now < occurrence.start:
                due.append((occurrence, offset))
    return due


def run_ics_source_tick(db: Session, source: IcsSource, now: datetime | None = None) -> int:
    """Checks `source` for due reminders against `now`. The due-check itself always runs - only
    the remote fetch is throttled to `refresh_minutes`, reusing `cached_ics_text` otherwise, so
    that how promptly a reminder fires depends on how often this is called (every scheduler tick,
    see run_all_ics_ticks), not on the feed's own refresh cadence."""
    now = now or datetime.now(UTC)
    last_synced_at = _as_datetime(source.last_synced_at) if source.last_synced_at else None
    due_for_refetch = (
        last_synced_at is None or now - last_synced_at >= timedelta(minutes=source.refresh_minutes)
    )
    if due_for_refetch or source.cached_ics_text is None:
        source.cached_ics_text = fetch_ics_text(source.url_or_path)
        source.last_synced_at = now

    lookahead = timedelta(minutes=max(source.offsets_minutes, default=0) + LOOKAHEAD_BUFFER_MINUTES)
    occurrences = expand_occurrences(source.cached_ics_text, now - timedelta(minutes=5), now + lookahead)

    created = 0
    for occurrence, offset in compute_due(occurrences, source.offsets_minutes, now):
        dedupe_key = f"ics:{source.id}:{occurrence.uid}:{occurrence.start.isoformat()}:{offset}"
        notification = enqueue_notification(
            db,
            source.user_id,
            rule_type=RuleType.ics_reminder,
            rule_id=source.id,
            dedupe_key=dedupe_key,
            title=f"In {offset} min: {occurrence.summary}",
            body=f"In {offset} min: {occurrence.summary} ({occurrence.start.strftime('%H:%M')})",
            channel=NotificationChannel.alert,
            kind=source.kind,
            dismissible=source.dismissible,
            snooze_minutes=source.snooze_minutes,
        )
        if notification is not None:  # None means already reminded for this event+offset
            created += 1

    db.commit()
    return created


def run_all_ics_ticks(db: Session, now: datetime | None = None) -> int:
    """Runs the due-check for every enabled source, every time this is called - see
    run_ics_source_tick for why that's unconditional while the feed re-fetch isn't. Call this on
    a short scheduler interval (app/config.py::ics_refresh_seconds); it's cheap for any source
    whose cache is still fresh."""
    now = now or datetime.now(UTC)
    total = 0
    for source in db.query(IcsSource).filter(IcsSource.enabled.is_(True)).all():
        total += run_ics_source_tick(db, source, now)
    return total
