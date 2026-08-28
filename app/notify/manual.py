"""Internal call for server-side code to push an ad-hoc reminder, bypassing the
daily-schedule/ICS rule seams. Just inserts a `pending` Notification like the scheduler jobs do -
the existing `_dispatch_tick` picks it up and sends it over the recipient's WebSocket, and the
companion app relays it to the watch. No separate delivery path."""

import uuid

from sqlalchemy.orm import Session

from app.models import Notification, ReminderKind, RuleType, User
from app.notify.queue import enqueue_notification


def push_notification(
    db: Session,
    user: User,
    *,
    body: str,
    title: str = "Reminder",
    kind: ReminderKind = ReminderKind.generic,
    dismissible: bool = True,
    snooze_minutes: list[int] | None = None,
) -> Notification:
    snooze_minutes = snooze_minutes or []
    if not dismissible and not snooze_minutes:
        # Same invariant as InfiniTime's ReminderController::Options - a non-dismissible
        # reminder with no snooze slots could never be cleared on-watch.
        raise ValueError("dismissible=False requires at least one snooze_minutes entry")

    rule_id = uuid.uuid4().hex
    notification = enqueue_notification(
        db,
        user.id,
        rule_type=RuleType.manual,
        rule_id=rule_id,
        dedupe_key=f"manual:{rule_id}",
        title=title,
        body=body,
        kind=kind,
        dismissible=dismissible,
        snooze_minutes=snooze_minutes,
    )
    assert notification is not None, "manual pushes use a fresh dedupe key and can't collide"
    return notification
