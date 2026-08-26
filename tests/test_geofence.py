from datetime import datetime, UTC

from app.models import Notification, PhoneLocation, RuleType, TodoItem, TodoList
from app.notify.geofence import check_todo_list_geofences, distance_m

# Roughly the Eiffel Tower and Notre-Dame, ~2.2km apart in Paris.
EIFFEL_TOWER = (48.8584, 2.2945)
NOTRE_DAME = (48.8530, 2.3499)


def _location(db_session, user, lat: float, lon: float) -> PhoneLocation:
    location = PhoneLocation(
        user_id=user.id, latitude=lat, longitude=lon, recorded_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    db_session.add(location)
    db_session.commit()
    db_session.refresh(location)
    return location


def _geofenced_list(db_session, user, *, radius_m: int = 200) -> TodoList:
    todo_list = TodoList(
        user_id=user.id,
        name="Groceries",
        caldav_url="https://caldav.example.com/groceries/",
        place_label="Corner store",
        place_latitude=EIFFEL_TOWER[0],
        place_longitude=EIFFEL_TOWER[1],
        place_radius_m=radius_m,
    )
    db_session.add(todo_list)
    db_session.commit()
    db_session.refresh(todo_list)
    return todo_list


def test_distance_m_matches_known_separation():
    d = distance_m(*EIFFEL_TOWER, *NOTRE_DAME)
    assert 3900 < d < 4300


def test_check_todo_list_geofences_ignores_lists_without_a_place(db_session, user):
    db_session.add(TodoList(user_id=user.id, name="No place", caldav_url="https://caldav.example.com/x/"))
    db_session.commit()
    location = _location(db_session, user, *EIFFEL_TOWER)

    created = check_todo_list_geofences(db_session, user.id, location)

    assert created == 0
    assert db_session.query(Notification).count() == 0


def test_check_todo_list_geofences_fires_on_entry(db_session, user):
    todo_list = _geofenced_list(db_session, user)
    inside = _location(db_session, user, *EIFFEL_TOWER)

    created = check_todo_list_geofences(db_session, user.id, inside)

    assert created == 1
    notification = db_session.query(Notification).one()
    assert notification.rule_type == RuleType.place_arrival
    assert notification.rule_id == todo_list.id
    assert "Corner store" in notification.title
    assert todo_list.place_inside is True


def test_check_todo_list_geofences_does_not_refire_while_still_inside(db_session, user):
    todo_list = _geofenced_list(db_session, user)
    check_todo_list_geofences(db_session, user.id, _location(db_session, user, *EIFFEL_TOWER))

    created_again = check_todo_list_geofences(
        db_session, user.id, _location(db_session, user, EIFFEL_TOWER[0] + 0.0001, EIFFEL_TOWER[1])
    )

    assert created_again == 0
    assert db_session.query(Notification).count() == 1
    assert todo_list.place_inside is True


def test_check_todo_list_geofences_refires_after_leaving_and_returning(db_session, user):
    todo_list = _geofenced_list(db_session, user)
    check_todo_list_geofences(db_session, user.id, _location(db_session, user, *EIFFEL_TOWER))

    outside = check_todo_list_geofences(db_session, user.id, _location(db_session, user, *NOTRE_DAME))
    assert outside == 0
    assert todo_list.place_inside is False

    back_inside = check_todo_list_geofences(db_session, user.id, _location(db_session, user, *EIFFEL_TOWER))

    assert back_inside == 1
    assert db_session.query(Notification).count() == 2


def test_check_todo_list_geofences_ignores_locations_outside_radius(db_session, user):
    _geofenced_list(db_session, user, radius_m=100)
    far = _location(db_session, user, *NOTRE_DAME)

    created = check_todo_list_geofences(db_session, user.id, far)

    assert created == 0


def test_check_todo_list_geofences_lists_pending_items_in_body(db_session, user):
    todo_list = _geofenced_list(db_session, user)
    db_session.add(TodoItem(todo_list_id=todo_list.id, uid="a", summary="Buy milk", completed=False))
    db_session.add(TodoItem(todo_list_id=todo_list.id, uid="b", summary="Buy eggs", completed=False))
    db_session.add(TodoItem(todo_list_id=todo_list.id, uid="c", summary="Done already", completed=True))
    db_session.commit()

    check_todo_list_geofences(db_session, user.id, _location(db_session, user, *EIFFEL_TOWER))

    notification = db_session.query(Notification).one()
    assert "Buy milk" in notification.body
    assert "Buy eggs" in notification.body
    assert "Done already" not in notification.body


def test_check_todo_list_geofences_reports_no_pending_items(db_session, user):
    _geofenced_list(db_session, user)

    check_todo_list_geofences(db_session, user.id, _location(db_session, user, *EIFFEL_TOWER))

    notification = db_session.query(Notification).one()
    assert notification.body == "No pending items"
