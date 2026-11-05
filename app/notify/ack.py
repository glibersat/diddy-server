import logging
from datetime import datetime, UTC

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import AckAction, Notification, NotificationChannel, NotificationStatus

logger = logging.getLogger("diddy.notify.ack")


def record_ack(db: Session, user_id: str, action: AckAction, snoozed_minutes: int) -> Notification | None:
    """Apply an inbound `ack` to whichever notification it's presumed to be about.

    The protocol carries no notification id (InfiniTime only tracks one active reminder at a
    time and the companion app is the source of truth for what it sent), so we match the most
    recently *sent* notification for this user - the same "one at a time" assumption the watch
    firmware makes.

    A snoozed reminder is still in play: the watch re-arms it on its own, with nothing sent
    through the server, so the next press on it arrives here with no new `sent` row to match.
    Without the snoozed rows below, that press is lost, and a DONE after a snooze reads as
    "snoozed" for good.
    """
    notification = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            or_(
                Notification.status == NotificationStatus.sent,
                and_(
                    Notification.status == NotificationStatus.acked,
                    Notification.ack_action == AckAction.snoozed,
                ),
            ),
            # Only reminders are ever acked on-watch - an alert that's still awaiting its
            # `delivered` must not soak up an ack meant for the reminder the wearer just cleared.
            Notification.channel == NotificationChannel.reminder,
        )
        .order_by(Notification.sent_at.desc(), Notification.created_at.desc())
        .first()
    )
    if notification is None:
        logger.warning("Received ack for user %s with no outstanding sent notification", user_id)
        return None

    query = db.query(Notification).filter(
        Notification.id == notification.id,
        Notification.status == notification.status,
        Notification.ack_action.is_(None)
        if notification.ack_action is None
        else Notification.ack_action == notification.ack_action,
    )
    updated = query.update(
        {
            Notification.status: NotificationStatus.acked,
            Notification.ack_action: action,
            Notification.ack_snoozed_minutes: snoozed_minutes,
            Notification.acked_at: datetime.now(UTC),
            Notification.snooze_count: Notification.snooze_count + int(action == AckAction.snoozed),
        },
        synchronize_session=False,
    )
    db.commit()
    db.refresh(notification)
    if not updated:
        logger.warning("Dropping ack for user %s: notification %s was requeued concurrently", user_id, notification.id)
        return None
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
        .order_by(Notification.sent_at.desc(), Notification.created_at.desc())
        .first()
    )
    if notification is None:
        logger.warning("Received delivered confirmation for user %s with no outstanding undelivered notification", user_id)
        return None

    values = {Notification.delivered_at: datetime.now(UTC)}
    if notification.channel == NotificationChannel.alert:
        values[Notification.status] = NotificationStatus.acked
    if not _update_if_still_sent(db, notification, values, undelivered=True):
        logger.warning(
            "Dropping delivered confirmation for user %s: notification %s was requeued concurrently", user_id, notification.id
        )
        return None
    return notification


def _update_if_still_sent(db: Session, notification: Notification, values: dict, undelivered: bool = False) -> bool:
    """Apply `values` only if `notification` is still in the state it was matched in - the
    requeue jobs run on APScheduler's thread pool and may have flipped it back to `pending` in
    between. If so, it'll be resent anyway, so dropping this message beats reattributing it to
    some other notification."""
    query = db.query(Notification).filter(
        Notification.id == notification.id, Notification.status == NotificationStatus.sent
    )
    if undelivered:
        query = query.filter(Notification.delivered_at.is_(None))
    updated = query.update(values, synchronize_session=False)
    db.commit()
    db.refresh(notification)
    return bool(updated)
