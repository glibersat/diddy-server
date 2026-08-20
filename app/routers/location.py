from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.models import PhoneLocation, User

router = APIRouter(prefix="/location", tags=["location"])


@router.get("", response_model=list[schemas.PhoneLocationOut])
def list_location(
    since: datetime | None = None,
    until: datetime | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PhoneLocation]:
    query = db.query(PhoneLocation).filter(PhoneLocation.user_id == user.id)
    if since is not None:
        query = query.filter(PhoneLocation.recorded_at >= since)
    if until is not None:
        query = query.filter(PhoneLocation.recorded_at <= until)
    return query.order_by(PhoneLocation.recorded_at.asc()).all()


@router.get("/latest", response_model=schemas.PhoneLocationOut)
def latest_location(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PhoneLocation:
    location = (
        db.query(PhoneLocation)
        .filter(PhoneLocation.user_id == user.id)
        .order_by(PhoneLocation.recorded_at.desc())
        .first()
    )
    if location is None:
        raise HTTPException(status_code=404, detail="No location reported yet")
    return location
