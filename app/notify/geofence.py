"""Fires a `place_arrival` Notification when the phone's reported position enters a TodoList's
geofence - see TodoList.place_inside in app/models.py for the entry/exit state that keeps this
from re-firing on every sample while the phone just sits there."""

import math
from datetime import datetime, UTC

from sqlalchemy.orm import Session

from app.models import Notification, PhoneLocation, RuleType, TodoItem, TodoList

_EARTH_RADIUS_M = 6_371_000
_MAX_LISTED_ITEMS = 5


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points - plenty accurate at the few-hundred-meter
    geofence radii this feature deals with; no need for anything more exact than haversine."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _pending_items_body(db: Session, todo_list: TodoList) -> str:
    items = (
        db.query(TodoItem)
        .filter(TodoItem.todo_list_id == todo_list.id, TodoItem.completed.is_(False))
        .order_by(TodoItem.due.asc())
        .all()
    )
    if not items:
        return "No pending items"
    summaries = [item.summary for item in items[:_MAX_LISTED_ITEMS]]
    if len(items) > _MAX_LISTED_ITEMS:
        summaries.append(f"+{len(items) - _MAX_LISTED_ITEMS} more")
    return ", ".join(summaries)


def check_todo_list_geofences(db: Session, user_id: str, location: PhoneLocation) -> int:
    """Compare `location` against every one of the user's enabled, geofenced TodoLists. A
    `place_arrival` reminder fires on the False -> True transition of `place_inside` only -
    staying inside (repeated samples while parked at the store) doesn't re-fire, and leaving
    resets it so the next visit fires again."""
    todo_lists = (
        db.query(TodoList)
        .filter(TodoList.user_id == user_id, TodoList.enabled.is_(True), TodoList.place_latitude.isnot(None))
        .all()
    )
    created = 0
    for todo_list in todo_lists:
        inside = (
            distance_m(location.latitude, location.longitude, todo_list.place_latitude, todo_list.place_longitude)
            <= todo_list.place_radius_m
        )
        if inside and not todo_list.place_inside:
            notification = Notification(
                user_id=user_id,
                rule_type=RuleType.place_arrival,
                rule_id=todo_list.id,
                dedupe_key=f"place:{todo_list.id}:{location.id}",
                scheduled_for=datetime.now(UTC),
                title=f"Near {todo_list.place_label or todo_list.name}",
                body=_pending_items_body(db, todo_list),
                kind=todo_list.kind,
                dismissible=todo_list.dismissible,
                snooze_minutes=todo_list.snooze_minutes,
            )
            db.add(notification)
            created += 1
        todo_list.place_inside = inside
    db.commit()
    return created
