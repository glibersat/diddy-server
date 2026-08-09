import logging
from datetime import datetime, timedelta, UTC

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Notification, NotificationStatus
from app.notify.connection_manager import manager

logger = logging.getLogger("diddy.notify.dispatcher")


def _trigger_payload(notification: Notification) -> dict:
    return {
        "type": "trigger",
        "kind": notification.kind,
        "easyDismiss": notification.dismissible,
        "snoozeMinutes": notification.snooze_minutes,
        "title": notification.title,
        "body": notification.body,
    }


async def dispatch_pending(db: Session) -> int:
    """Send every `pending` Notification as a `trigger` over its user's companion WebSocket.

    A successful send only means the phone received it - not that the watch showed it, and
    definitely not that the wearer acted on it. `requeue_unacked` is what handles that gap.
    """
    pending = db.query(Notification).filter(Notification.status == NotificationStatus.pending).all()
    now = datetime.now(UTC)
    for notification in pending:
        delivered = await manager.send_to_user(notification.user_id, _trigger_payload(notification))
        notification.send_attempts += 1
        if delivered:
            notification.status = NotificationStatus.sent
            notification.sent_at = now
        elif notification.send_attempts >= settings.max_send_attempts:
            notification.status = NotificationStatus.failed
            notification.error = "No connected device after max_send_attempts"
        # else: stays `pending`, picked up again on the next dispatch tick
    db.commit()
    return len(pending)


def requeue_undelivered(db: Session, now: datetime | None = None) -> int:
    """Resend notifications the phone hasn't confirmed reached the watch within
    `delivery_timeout_seconds`.

    A successful send to `manager.send_to_user` only proves the phone's WebSocket accepted the
    bytes - if the phone isn't currently connected to the watch over BLE (out of range, watch
    off, etc.) it drops the trigger with no signal back to us at all (see
    companion-android/docs/backend-protocol.md). The only positive confirmation is a `delivered`
    message, sent once the phone's BLE write of the Trigger characteristic actually completes -
    so anything still `sent` with no `delivered_at` after the timeout gets treated as dropped and
    resent, same as if the WebSocket send itself had failed.
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.delivery_timeout_seconds)
    stale = (
        db.query(Notification)
        .filter(
            Notification.status == NotificationStatus.sent,
            Notification.delivered_at.is_(None),
            Notification.sent_at <= cutoff,
        )
        .all()
    )
    for notification in stale:
        if notification.send_attempts >= settings.max_send_attempts:
            notification.status = NotificationStatus.failed
            notification.error = "No delivery confirmation received after max_send_attempts"
        else:
            notification.status = NotificationStatus.pending
    db.commit()
    return len(stale)


def requeue_unacked(db: Session, now: datetime | None = None) -> int:
    """Resend notifications that reached the watch but were never acked within
    `ack_timeout_seconds` - the wearer never snoozed/dismissed it, so nag again.

    This only runs once a notification is at least `delivered` (see `requeue_undelivered` for the
    earlier, transport-level gap this doesn't cover): resending here is redundant with that faster
    loop for anything that never got delivered in the first place.
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.ack_timeout_seconds)
    stale = (
        db.query(Notification)
        .filter(
            Notification.status == NotificationStatus.sent,
            Notification.delivered_at.isnot(None),
            Notification.sent_at <= cutoff,
        )
        .all()
    )
    for notification in stale:
        if notification.send_attempts >= settings.max_send_attempts:
            notification.status = NotificationStatus.failed
            notification.error = "No ack received after max_send_attempts"
        else:
            notification.status = NotificationStatus.pending
            notification.delivered_at = None
    db.commit()
    return len(stale)
