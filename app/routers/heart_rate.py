from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.models import HeartRateReading, User

router = APIRouter(prefix="/heart-rate", tags=["heart-rate"])


@router.get("", response_model=list[schemas.HeartRateReadingOut])
def list_heart_rate(
    since: datetime | None = None,
    until: datetime | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[HeartRateReading]:
    query = db.query(HeartRateReading).filter(HeartRateReading.user_id == user.id)
    if since is not None:
        query = query.filter(HeartRateReading.recorded_at >= since)
    if until is not None:
        query = query.filter(HeartRateReading.recorded_at <= until)
    return query.order_by(HeartRateReading.recorded_at.asc()).all()
