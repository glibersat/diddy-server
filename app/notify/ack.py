import logging
from datetime import datetime, UTC

from sqlalchemy.orm import Session

from app.models import AckAction, Notification, NotificationStatus

logger = logging.getLogger("diddy.notify.ack")


def record_ack(db: Session, user_id: str, notification_id: str | None, action: AckAction, snoozed_minutes: int) -> Notification | None:
    """Apply an inbound `ack` to the notification it names.

    `notification_id` can be null - the companion app couldn't resolve the watch's ack back to a
    specific notification (see AckMessage in app/schemas.py) - in which case there's nothing to
    apply this to; still logged, since a wearer action the backend can't attribute anywhere is
    worth knowing about even if it can't update a row.
    """
    if notification_id is None:
        logger.warning("Received ack for user %s with no notification_id, unable to record", user_id)
        return None

    notification = (
        db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user_id).first()
    )
    if notification is None:
        logger.warning("Received ack for user %s referencing unknown notification %s", user_id, notification_id)
        return None

    notification.status = NotificationStatus.acked
    notification.ack_action = action
    notification.ack_snoozed_minutes = snoozed_minutes
    notification.acked_at = datetime.now(UTC)
    db.commit()
    return notification


def record_delivered(db: Session, user_id: str, notification_id: str | None) -> Notification | None:
    """Apply an inbound `delivered` confirmation to the notification it names. Only matches a
    notification not already marked delivered, so a late/duplicate `delivered` doesn't clobber a
    later, unrelated delivery timestamp.
    """
    if notification_id is None:
        logger.warning("Received delivered confirmation for user %s with no notification_id, unable to record", user_id)
        return None

    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            Notification.delivered_at.is_(None),
        )
        .first()
    )
    if notification is None:
        logger.warning(
            "Received delivered confirmation for user %s referencing unknown/already-delivered notification %s",
            user_id,
            notification_id,
        )
        return None

    notification.delivered_at = datetime.now(UTC)
    db.commit()
    return notification
