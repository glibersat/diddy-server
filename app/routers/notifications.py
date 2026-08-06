from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[schemas.NotificationOut])
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.scheduled_for.desc())
        .limit(200)
        .all()
    )
