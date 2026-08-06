from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.models import DailySchedule, User

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _get_owned(db: Session, user: User, schedule_id: str) -> DailySchedule:
    schedule = (
        db.query(DailySchedule)
        .filter(DailySchedule.id == schedule_id, DailySchedule.user_id == user.id)
        .first()
    )
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    return schedule


@router.post("", response_model=schemas.DailyScheduleOut)
def create_schedule(
    payload: schemas.DailyScheduleCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailySchedule:
    schedule = DailySchedule(user_id=user.id, **payload.model_dump())
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.get("", response_model=list[schemas.DailyScheduleOut])
def list_schedules(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[DailySchedule]:
    return db.query(DailySchedule).filter(DailySchedule.user_id == user.id).all()


@router.patch("/{schedule_id}", response_model=schemas.DailyScheduleOut)
def update_schedule(
    schedule_id: str,
    payload: schemas.DailyScheduleUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailySchedule:
    schedule = _get_owned(db, user, schedule_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(schedule, key, value)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    schedule = _get_owned(db, user, schedule_id)
    db.delete(schedule)
    db.commit()
