from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=schemas.UserOut)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)) -> User:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(409, "Email already registered")
    user = User(email=payload.email, timezone=payload.timezone)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=schemas.UserOut)
def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    payload: schemas.UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user
