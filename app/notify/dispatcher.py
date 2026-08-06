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


def requeue_unacked(db: Session, now: datetime | None = None) -> int:
    """Resend notifications that were delivered but never acked within `ack_timeout_seconds`.

    Delivery/ack over this protocol is fire-and-forget with no guarantee (see
    doc/ReminderService.md and companion-android/docs/backend-protocol.md) - a dropped trigger
    or an unseen watch alert looks identical to the backend, so re-sending is the only way to
    approximate a delivery guarantee.
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.ack_timeout_seconds)
    stale = (
        db.query(Notification)
        .filter(Notification.status == NotificationStatus.sent, Notification.sent_at <= cutoff)
        .all()
    )
    for notification in stale:
        if notification.send_attempts >= settings.max_send_attempts:
            notification.status = NotificationStatus.failed
            notification.error = "No ack received after max_send_attempts"
        else:
            notification.status = NotificationStatus.pending
    db.commit()
    return len(stale)
