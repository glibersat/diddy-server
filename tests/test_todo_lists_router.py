import pytest
from pydantic import ValidationError

from app import schemas
from app.models import TodoList
from app.routers import todo_lists


def test_create_list_persists_and_never_returns_the_password(db_session, user):
    payload = schemas.TodoListCreate(
        name="Groceries",
        caldav_url="https://caldav.example.com/groceries/",
        username="ada",
        password="hunter2",
        dismissible=True,
    )

    todo_list = todo_lists.create_list(payload, user, db_session)
    out = schemas.TodoListOut.model_validate(todo_list)

    assert todo_list.password == "hunter2"  # stored, so sync can authenticate
    assert "password" not in out.model_dump()  # but never serialized back out


def test_todo_list_create_requires_all_place_fields_together():
    with pytest.raises(ValidationError):
        schemas.TodoListCreate(
            name="Groceries",
            caldav_url="https://caldav.example.com/groceries/",
            dismissible=True,
            place_latitude=48.85,
            # place_longitude / place_radius_m missing
        )


def test_todo_list_create_rejects_non_hundred_radius():
    with pytest.raises(ValidationError):
        schemas.TodoListCreate(
            name="Groceries",
            caldav_url="https://caldav.example.com/groceries/",
            dismissible=True,
            place_label="Store",
            place_latitude=48.85,
            place_longitude=2.35,
            place_radius_m=150,
        )


def test_update_list_can_clear_a_place(db_session, user):
    todo_list = TodoList(
        user_id=user.id,
        name="Groceries",
        caldav_url="https://caldav.example.com/groceries/",
        place_label="Store",
        place_latitude=48.85,
        place_longitude=2.35,
        place_radius_m=200,
        place_inside=True,
    )
    db_session.add(todo_list)
    db_session.commit()

    updated = todo_lists.update_list(
        todo_list.id, schemas.TodoListUpdate(clear_place=True), user, db_session
    )

    assert updated.place_latitude is None
    assert updated.place_longitude is None
    assert updated.place_radius_m is None
    assert updated.place_inside is False


def test_list_lists_only_returns_the_owning_users_lists(db_session, user):
    other_payload = schemas.TodoListCreate(
        name="Not mine", caldav_url="https://caldav.example.com/x/", dismissible=True
    )
    from app.models import User

    other_user = User(email="other@example.com")
    db_session.add(other_user)
    db_session.commit()
    todo_lists.create_list(other_payload, other_user, db_session)

    mine = schemas.TodoListCreate(
        name="Mine", caldav_url="https://caldav.example.com/y/", dismissible=True
    )
    todo_lists.create_list(mine, user, db_session)

    result = todo_lists.list_lists(user, db_session)

    assert [t.name for t in result] == ["Mine"]
