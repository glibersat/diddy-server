from datetime import datetime, UTC
from pathlib import Path

from icalendar import Calendar

from app.models import TodoItem, TodoList
from app.scheduler.todo import run_todo_list_tick

FIXTURE = Path(__file__).parent / "fixtures" / "sample_todos.ics"


def _components(ics_text: str):
    return Calendar.from_ical(ics_text).walk("VTODO")


def _list(db_session, user) -> TodoList:
    todo_list = TodoList(user_id=user.id, name="Groceries", caldav_url="https://caldav.example.com/groceries/")
    db_session.add(todo_list)
    db_session.commit()
    db_session.refresh(todo_list)
    return todo_list


def test_run_todo_list_tick_creates_items(db_session, user, monkeypatch):
    monkeypatch.setattr(
        "app.scheduler.todo.fetch_todo_components", lambda todo_list: _components(FIXTURE.read_text())
    )
    todo_list = _list(db_session, user)

    now = datetime(2024, 1, 3, tzinfo=UTC)
    synced = run_todo_list_tick(db_session, todo_list, now=now)

    items = db_session.query(TodoItem).filter(TodoItem.todo_list_id == todo_list.id).all()
    assert synced == 3
    assert {i.uid for i in items} == {"todo-1@example.com", "todo-2@example.com", "todo-3@example.com"}
    completed = {i.uid: i.completed for i in items}
    assert completed["todo-1@example.com"] is False
    assert completed["todo-3@example.com"] is True
    due = next(i.due for i in items if i.uid == "todo-2@example.com")
    assert due == datetime(2024, 1, 5, 9, 0, tzinfo=UTC)
    assert todo_list.last_synced_at == now


def test_run_todo_list_tick_upserts_on_second_sync(db_session, user, monkeypatch):
    """A re-sync updates existing rows by uid rather than duplicating them - status flips from
    NEEDS-ACTION to COMPLETED upstream should be reflected, not appended as a new row."""
    monkeypatch.setattr(
        "app.scheduler.todo.fetch_todo_components", lambda todo_list: _components(FIXTURE.read_text())
    )
    todo_list = _list(db_session, user)
    run_todo_list_tick(db_session, todo_list)

    updated_ics = FIXTURE.read_text().replace(
        "UID:todo-1@example.com\nDTSTAMP:20240101T000000Z\nSUMMARY:Buy milk\nSTATUS:NEEDS-ACTION",
        "UID:todo-1@example.com\nDTSTAMP:20240101T000000Z\nSUMMARY:Buy milk\nSTATUS:COMPLETED",
    )
    monkeypatch.setattr("app.scheduler.todo.fetch_todo_components", lambda todo_list: _components(updated_ics))
    run_todo_list_tick(db_session, todo_list)

    items = db_session.query(TodoItem).filter(TodoItem.todo_list_id == todo_list.id).all()
    assert len(items) == 3  # still 3 rows, not 6
    milk = next(i for i in items if i.uid == "todo-1@example.com")
    assert milk.completed is True


def test_run_todo_list_tick_removes_items_no_longer_upstream(db_session, user, monkeypatch):
    monkeypatch.setattr(
        "app.scheduler.todo.fetch_todo_components", lambda todo_list: _components(FIXTURE.read_text())
    )
    todo_list = _list(db_session, user)
    run_todo_list_tick(db_session, todo_list)

    shrunk_ics = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VTODO
UID:todo-1@example.com
DTSTAMP:20240101T000000Z
SUMMARY:Buy milk
STATUS:NEEDS-ACTION
END:VTODO
END:VCALENDAR
"""
    monkeypatch.setattr("app.scheduler.todo.fetch_todo_components", lambda todo_list: _components(shrunk_ics))
    run_todo_list_tick(db_session, todo_list)

    items = db_session.query(TodoItem).filter(TodoItem.todo_list_id == todo_list.id).all()
    assert {i.uid for i in items} == {"todo-1@example.com"}
