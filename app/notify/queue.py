"""Shared insertion logic for pending `Notification` rows, used by anything that queues a
notification ahead of time for app/notify/dispatcher.py to send and retry - as opposed to
sending immediately and ephemerally with no persistence (see app/notify/alert.py::send_alert,
app/routers/phone.py::ring_phone for that)."""

from datetime import datetime, timedelta, UTC

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Notification, NotificationChannel, ReminderKind, RuleType
from app.notify.dispatcher import wake


def enqueue_notification(
    db: Session,
    user_id: str,
    *,
    rule_type: RuleType,
    rule_id: str,
    dedupe_key: str,
    title: str,
    body: str,
    channel: NotificationChannel = NotificationChannel.reminder,
    kind: ReminderKind = ReminderKind.generic,
    dismissible: bool = True,
    snooze_minutes: list[int] | None = None,
    expires_at: datetime | None = None,
    scheduled_for: datetime | None = None,
) -> Notification | None:
    """Inserts a `pending` Notification and wakes the dispatch loop; `dispatch_pending`
    (dispatcher.py) picks it up from there and sends it over the recipient's WebSocket, retrying per app/config.py's settings
    until it's delivered (or, for `channel=reminder`, acked).

    Returns None instead of raising if `dedupe_key` collides with an existing row - callers that
    dedupe on a stable key (ICS occurrences, daily schedule ticks) expect a silent no-op for
    something already queued, not an error.

    `scheduled_for` defaults to now; the dispatcher leaves a later row alone until it's due.
    `expires_at` defaults to app/config.py's `notification_ttl_hours` after that (see
    Notification.expires_at) - pass something tighter when the notification goes stale sooner.
    """
    due = scheduled_for or datetime.now(UTC)
    notification = Notification(
        user_id=user_id,
        rule_type=rule_type,
        rule_id=rule_id,
        dedupe_key=dedupe_key,
        scheduled_for=due,
        title=title,
        body=body,
        channel=channel,
        kind=kind,
        dismissible=dismissible,
        snooze_minutes=snooze_minutes or [],
    )
    notification.expires_at = expires_at or due + timedelta(hours=settings.notification_ttl_hours)
    db.add(notification)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(notification)
    wake()
    return notification
