import logging
from datetime import datetime, UTC

from sqlalchemy.orm import Session

from app.models import AckAction, Notification, NotificationChannel, NotificationStatus

logger = logging.getLogger("diddy.notify.ack")


def record_ack(db: Session, user_id: str, action: AckAction, snoozed_minutes: int) -> Notification | None:
    """Apply an inbound `ack` to whichever notification it's presumed to be about.

    The protocol carries no notification id (InfiniTime only tracks one active reminder at a
    time and the companion app is the source of truth for what it sent), so we match the most
    recently *sent* notification for this user - the same "one at a time" assumption the watch
    firmware makes.
    """
    notification = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.status == NotificationStatus.sent)
        .order_by(Notification.sent_at.desc())
        .first()
    )
    if notification is None:
        logger.warning("Received ack for user %s with no outstanding sent notification", user_id)
        return None

    notification.status = NotificationStatus.acked
    notification.ack_action = action
    notification.ack_snoozed_minutes = snoozed_minutes
    notification.acked_at = datetime.now(UTC)
    db.commit()
    return notification


def record_delivered(db: Session, user_id: str) -> Notification | None:
    """Apply an inbound `delivered` confirmation to whichever notification it's presumed to be
    about - same "match the most recently sent notification for this user" assumption as
    `record_ack`, since the protocol carries no notification id. Only matches a notification not
    already marked delivered, so a late/duplicate `delivered` for an already-confirmed send
    doesn't reattribute itself to whatever's sent since.

    `channel=alert` notifications have no separate on-watch ack step (see
    app/models.py::NotificationChannel), so this closes their lifecycle out immediately by
    marking them `acked` too - otherwise they'd sit at `sent` forever and never be picked up by
    `requeue_unacked`'s nag loop, which expects an ack that will never come.
    """
    notification = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.status == NotificationStatus.sent,
            Notification.delivered_at.is_(None),
        )
        .order_by(Notification.sent_at.desc())
        .first()
    )
    if notification is None:
        logger.warning("Received delivered confirmation for user %s with no outstanding undelivered notification", user_id)
        return None

    notification.delivered_at = datetime.now(UTC)
    if notification.channel == NotificationChannel.alert:
        notification.status = NotificationStatus.acked
    db.commit()
    return notification
