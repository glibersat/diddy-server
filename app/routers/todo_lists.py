from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.models import TodoItem, TodoList, User
from app.scheduler.todo import fetch_todo_components

router = APIRouter(prefix="/todo-lists", tags=["todo-lists"])


def _get_owned(db: Session, user: User, list_id: str) -> TodoList:
    todo_list = db.query(TodoList).filter(TodoList.id == list_id, TodoList.user_id == user.id).first()
    if not todo_list:
        raise HTTPException(404, "Todo list not found")
    return todo_list


@router.post("/test-connection", response_model=schemas.TodoListConnectionResult)
def test_connection(
    payload: schemas.TodoListConnectionTest,
    user: User = Depends(get_current_user),
) -> schemas.TodoListConnectionResult:
    """Try the CalDAV credentials/URL a user is about to save, without persisting anything -
    lets the form catch a typo'd URL or bad password before the first sync tick (which runs
    unattended and only surfaces failures as a stuck `last_synced_at`)."""
    probe = TodoList(caldav_url=payload.caldav_url, username=payload.username, password=payload.password)
    try:
        fetch_todo_components(probe)
    except Exception as e:
        return schemas.TodoListConnectionResult(ok=False, detail=str(e))
    return schemas.TodoListConnectionResult(ok=True)


@router.post("", response_model=schemas.TodoListOut)
def create_list(
    payload: schemas.TodoListCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TodoList:
    todo_list = TodoList(user_id=user.id, **payload.model_dump())
    db.add(todo_list)
    db.commit()
    db.refresh(todo_list)
    return todo_list


@router.get("", response_model=list[schemas.TodoListOut])
def list_lists(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[TodoList]:
    return db.query(TodoList).filter(TodoList.user_id == user.id).all()


@router.patch("/{list_id}", response_model=schemas.TodoListOut)
def update_list(
    list_id: str,
    payload: schemas.TodoListUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TodoList:
    todo_list = _get_owned(db, user, list_id)
    updates = payload.model_dump(exclude_unset=True, exclude={"clear_place"})
    if payload.clear_place:
        updates.update(place_label=None, place_latitude=None, place_longitude=None, place_radius_m=None)
        todo_list.place_inside = False
    for key, value in updates.items():
        setattr(todo_list, key, value)
    db.commit()
    db.refresh(todo_list)
    return todo_list


@router.delete("/{list_id}", status_code=204)
def delete_list(list_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    todo_list = _get_owned(db, user, list_id)
    db.delete(todo_list)
    db.commit()


@router.get("/{list_id}/items", response_model=list[schemas.TodoItemOut])
def list_items(
    list_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TodoItem]:
    todo_list = _get_owned(db, user, list_id)
    return (
        db.query(TodoItem)
        .filter(TodoItem.todo_list_id == todo_list.id)
        .order_by(TodoItem.completed.asc(), TodoItem.due.asc())
        .all()
    )
