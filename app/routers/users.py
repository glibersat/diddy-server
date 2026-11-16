from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.models import User
from app.notify.connection_manager import manager

router = APIRouter(prefix="/users", tags=["users"])


def _out(user: User) -> schemas.UserOut:
    out = schemas.UserOut.model_validate(user)
    out.phone_connected = manager.is_connected(user.id)
    return out


@router.post("", response_model=schemas.UserOut)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)) -> schemas.UserOut:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(409, "Email already registered")
    user = User(email=payload.email, timezone=payload.timezone)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _out(user)


@router.get("/me", response_model=schemas.UserOut)
def get_me(user: User = Depends(get_current_user)) -> schemas.UserOut:
    return _out(user)


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    payload: schemas.UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.UserOut:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return _out(user)
