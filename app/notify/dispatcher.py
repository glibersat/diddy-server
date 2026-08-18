import logging
from datetime import datetime, timedelta, UTC

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Notification, NotificationStatus, RuleType
from app.notify.connection_manager import manager

logger = logging.getLogger("diddy.notify.dispatcher")


def _trigger_payload(notification: Notification) -> dict:
    return {
        "type": "trigger",
        "notification_id": notification.id,
        "kind": notification.kind,
        "easyDismiss": notification.dismissible,
        "snoozeMinutes": notification.snooze_minutes,
        "title": notification.title,
        "body": notification.body,
    }


def _schedule_payload(notification: Notification) -> dict:
    """See companion-android/docs/backend-protocol.md's `schedule` message and
    ReminderService.md's Schedule characteristic - `fireAt` is the watch's cue to fire this
    locally, independent of any connection at that time."""
    return {
        "type": "schedule",
        "notification_id": notification.id,
        "fireAt": int(notification.scheduled_for.timestamp()),
        "kind": notification.kind,
        "easyDismiss": notification.dismissible,
        "snoozeMinutes": notification.snooze_minutes,
        "title": notification.title,
        "body": notification.body,
    }


def _payload_for(notification: Notification, now: datetime) -> dict:
    """`manual` pushes and anything already due are sent live (`trigger`); anything with a known
    future fire time is pushed ahead as a `schedule`, so it's on-watch well before it needs to
    fire - see daily.py/ics.py, which now enqueue occurrences ahead of time rather than at the
    exact matching tick."""
    if notification.rule_type == RuleType.manual or notification.scheduled_for <= now:
        return _trigger_payload(notification)
    return _schedule_payload(notification)


async def dispatch_pending(db: Session, user_id: str | None = None) -> int:
    """Send every `pending` Notification as a `trigger` or `schedule` over its user's companion
    WebSocket, depending on whether it's already due - see `_payload_for`.

    A successful send only means the phone received it - not that the watch showed/stored it, and
    definitely not that the wearer acted on it. `requeue_unacked` is what handles that gap.

    `user_id` scopes this to one user's notifications - used by `resend_now` so a single watch
    reconnecting doesn't also churn through every other user's pending queue.
    """
    query = db.query(Notification).filter(Notification.status == NotificationStatus.pending)
    if user_id is not None:
        query = query.filter(Notification.user_id == user_id)
    pending = query.all()
    now = datetime.now(UTC)
    for notification in pending:
        delivered = await manager.send_to_user(notification.user_id, _payload_for(notification, now))
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


async def send_cancel(notification: Notification) -> bool:
    """Tells the phone to remove a not-yet-fired `schedule` it already has - e.g. the underlying
    DailySchedule/IcsSource changed or was removed after the occurrence was pushed. Caller is
    responsible for the Notification row itself (typically deleting it); this only notifies the
    phone/watch. Returns whatever `send_to_user` returns - false just means nothing was connected
    to tell right now, same "fire and forget, no retry" contract `trigger` has always had.
    """
    return await manager.send_to_user(notification.user_id, {"type": "cancel", "notification_id": notification.id})


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


async def resend_now(db: Session, user_id: str) -> int:
    """Called when the companion app reports its BLE connection to the watch just became ready
    again (`watch_ready` over the WS) - retry anything we handed to this phone but never got a
    `delivered` confirmation for, instead of waiting out `requeue_undelivered`'s timeout.

    Also revives anything that already gave up (`failed`): `max_send_attempts` is tuned for how
    fast a *reachable* device should ack, not for how long a watch might reasonably be away, so a
    notification can easily exhaust its attempt budget and land in `failed` well before the wearer
    actually reconnects. Without this, "watch was away for a while, then reconnected" - the exact
    case `watch_ready` exists to handle - reconnected to a dead end: `dispatch_pending` only looks
    at `pending`, so nothing would ever pick a `failed` row back up. A reconnect gets a fresh
    attempt budget, since exhausting the old one was about the earlier disconnected stretch, not
    this attempt.
    """
    stale = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            or_(
                and_(Notification.status == NotificationStatus.sent, Notification.delivered_at.is_(None)),
                Notification.status == NotificationStatus.failed,
            ),
        )
        .all()
    )
    for notification in stale:
        if notification.status == NotificationStatus.failed:
            notification.send_attempts = 0
            notification.error = None
        notification.status = NotificationStatus.pending
    db.commit()
    return await dispatch_pending(db, user_id=user_id)


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
