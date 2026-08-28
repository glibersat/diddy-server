"""Shared insertion logic for pending `Notification` rows, used by anything that queues a
notification ahead of time for app/notify/dispatcher.py to send and retry - as opposed to
sending immediately and ephemerally with no persistence (see app/notify/alert.py::send_alert,
app/routers/phone.py::ring_phone for that)."""

from datetime import datetime, UTC

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Notification, NotificationChannel, ReminderKind, RuleType


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
) -> Notification | None:
    """Inserts a `pending` Notification; `dispatch_pending` (dispatcher.py) picks it up from
    there and sends it over the recipient's WebSocket, retrying per app/config.py's settings
    until it's delivered (or, for `channel=reminder`, acked).

    Returns None instead of raising if `dedupe_key` collides with an existing row - callers that
    dedupe on a stable key (ICS occurrences, daily schedule ticks) expect a silent no-op for
    something already queued, not an error.
    """
    notification = Notification(
        user_id=user_id,
        rule_type=rule_type,
        rule_id=rule_id,
        dedupe_key=dedupe_key,
        scheduled_for=datetime.now(UTC),
        title=title,
        body=body,
        channel=channel,
        kind=kind,
        dismissible=dismissible,
        snooze_minutes=snooze_minutes or [],
    )
    db.add(notification)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(notification)
    return notification
