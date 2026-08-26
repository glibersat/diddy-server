"""Sync a TodoList's VTODOs from its CalDAV calendar - the todo-list counterpart to
app/scheduler/ics.py's VEVENT sync. Notifications aren't created here; a synced list is only a
source of pending items for app/notify/geofence.py to report when the phone arrives nearby."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, UTC

import caldav
from icalendar import Calendar as ICalendar
from sqlalchemy.orm import Session

from app.models import TodoItem, TodoList


@dataclass
class TodoSummary:
    uid: str
    summary: str
    due: datetime | None
    completed: bool


def _as_datetime(value: date | datetime | None) -> datetime | None:
    """Same convention as app/scheduler/ics.py::_as_datetime - a date-only DUE has no meaningful
    ordering against `datetime.now()`, so it's dropped rather than guessed at."""
    if value is None or not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def fetch_todo_components(todo_list: TodoList) -> list:
    """Connect to the CalDAV calendar and return every VTODO component, completed or not -
    filtering to "still pending" happens downstream (app/notify/geofence.py), since a completed
    item still needs to be upserted here to clear its `completed` flag once it's checked off
    upstream."""
    client = caldav.DAVClient(
        url=todo_list.caldav_url, username=todo_list.username, password=todo_list.password
    )
    calendar = caldav.Calendar(client=client, url=todo_list.caldav_url)
    components = []
    for todo in calendar.todos(include_completed=True):
        components.extend(ICalendar.from_ical(todo.data).walk("VTODO"))
    return components


def _parse_todo(component) -> TodoSummary:
    uid = str(component.get("UID"))
    summary = str(component.get("SUMMARY", "Todo"))
    due_prop = component.get("DUE")
    due = _as_datetime(due_prop.dt) if due_prop else None
    status = str(component.get("STATUS", "")).upper()
    completed = status == "COMPLETED"
    return TodoSummary(uid=uid, summary=summary, due=due, completed=completed)


def run_todo_list_tick(db: Session, todo_list: TodoList, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    components = fetch_todo_components(todo_list)

    seen_uids = set()
    synced = 0
    for component in components:
        parsed = _parse_todo(component)
        seen_uids.add(parsed.uid)
        item = (
            db.query(TodoItem)
            .filter(TodoItem.todo_list_id == todo_list.id, TodoItem.uid == parsed.uid)
            .first()
        )
        if item is None:
            item = TodoItem(todo_list_id=todo_list.id, uid=parsed.uid)
            db.add(item)
        item.summary = parsed.summary
        item.due = parsed.due
        item.completed = parsed.completed
        synced += 1

    # Drop items no longer present upstream - deleted, or the list was re-pointed at a
    # different calendar. notin_([]) is still true for every row, so an empty upstream list
    # correctly clears everything.
    db.query(TodoItem).filter(TodoItem.todo_list_id == todo_list.id, TodoItem.uid.notin_(seen_uids)).delete(
        synchronize_session=False
    )

    todo_list.last_synced_at = now
    db.commit()
    return synced


def run_all_todo_ticks(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    total = 0
    for todo_list in db.query(TodoList).filter(TodoList.enabled.is_(True)).all():
        last_synced_at = _as_datetime(todo_list.last_synced_at) if todo_list.last_synced_at else None
        due_for_refresh = (
            last_synced_at is None or now - last_synced_at >= timedelta(minutes=todo_list.refresh_minutes)
        )
        if due_for_refresh:
            total += run_todo_list_tick(db, todo_list, now)
    return total
