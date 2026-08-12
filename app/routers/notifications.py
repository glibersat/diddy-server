from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.models import Notification, User
from app.notify.next_up import NextReminder, next_reminder

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


@router.get("/next", response_model=schemas.NextReminderOut | None)
def get_next_notification(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> NextReminder | None:
    return next_reminder(db, user.id)
