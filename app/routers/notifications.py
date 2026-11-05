import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.models import Notification, NotificationStatus, RuleType, User
from app.notify.next_up import NextReminder, next_reminder
from app.notify.queue import enqueue_notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[schemas.NotificationOut])
def list_notifications(
    limit: int = Query(default=200, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.scheduled_for.desc())
        .limit(limit)
        .all()
    )


@router.post("", response_model=schemas.NotificationOut, status_code=status.HTTP_201_CREATED)
def create_notification(
    payload: schemas.NotificationCreate,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Notification:
    """Queue a notification. Sending the same `dedupe_key` again returns the first one with a 200."""
    # Keys are unique across the whole table, so one user's key must not be able to block another's.
    dedupe_key = f"api:{user.id}:{payload.dedupe_key}"
    notification = enqueue_notification(
        db,
        user.id,
        rule_type=RuleType.manual,
        rule_id=uuid.uuid4().hex,
        dedupe_key=dedupe_key,
        title=payload.title,
        body=payload.body,
        channel=payload.channel,
        kind=payload.kind,
        dismissible=payload.dismissible,
        snooze_minutes=payload.snooze_minutes,
        scheduled_for=payload.scheduled_for,
    )
    if notification is not None:
        return notification
    response.status_code = status.HTTP_200_OK
    return db.query(Notification).filter(Notification.dedupe_key == dedupe_key).one()


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_notification(
    notification_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    """Cancel a notification that hasn't gone out yet."""
    query = db.query(Notification).filter(
        Notification.id == notification_id, Notification.user_id == user.id
    )
    if query.first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    cancelled = query.filter(
        Notification.status == NotificationStatus.pending, Notification.sent_at.is_(None)
    ).delete(synchronize_session=False)
    db.commit()
    if not cancelled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Notification has already gone out")


@router.get("/next", response_model=schemas.NextReminderOut | None)
def get_next_notification(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> NextReminder | None:
    return next_reminder(db, user.id)
