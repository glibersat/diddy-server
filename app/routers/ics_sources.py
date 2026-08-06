from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.models import IcsSource, User

router = APIRouter(prefix="/ics-sources", tags=["ics-sources"])


def _get_owned(db: Session, user: User, source_id: str) -> IcsSource:
    source = db.query(IcsSource).filter(IcsSource.id == source_id, IcsSource.user_id == user.id).first()
    if not source:
        raise HTTPException(404, "ICS source not found")
    return source


@router.post("", response_model=schemas.IcsSourceOut)
def create_source(
    payload: schemas.IcsSourceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IcsSource:
    source = IcsSource(user_id=user.id, **payload.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("", response_model=list[schemas.IcsSourceOut])
def list_sources(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[IcsSource]:
    return db.query(IcsSource).filter(IcsSource.user_id == user.id).all()


@router.patch("/{source_id}", response_model=schemas.IcsSourceOut)
def update_source(
    source_id: str,
    payload: schemas.IcsSourceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IcsSource:
    source = _get_owned(db, user, source_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    source = _get_owned(db, user, source_id)
    db.delete(source)
    db.commit()
