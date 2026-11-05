import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, UTC

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Notification, NotificationChannel, NotificationStatus, ReminderKind
from app.notify.connection_manager import manager

logger = logging.getLogger("diddy.notify.dispatcher")


def _dispatch_payload(notification: Notification) -> dict:
    """Wire format depends on `channel` - see app/models.py::NotificationChannel. `alert` uses
    the BLE-standard Alert Notification Service on the phone side (just a message, no
    dismiss/snooze/kind); `reminder` uses the custom Reminder/Trigger characteristic."""
    if notification.channel == NotificationChannel.alert:
        return {"type": "alert", "message": notification.body}
    return {
        "type": "trigger",
        "kind": notification.kind,
        "easyDismiss": notification.dismissible,
        "snoozeMinutes": notification.snooze_minutes,
        "title": notification.title,
        "body": notification.body,
    }


# Serializes dispatch per user, so the scheduler's `_dispatch_tick` and a `watch_ready`-driven
# `resend_now` for the same user can't interleave their sends - the watch holds one reminder at
# a time, so send order matters, and `record_ack`/`record_delivered` attribute by it.
_user_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# Bound by `run_dispatch_loop` while it runs; until then (and in tests) `wake` is a no-op.
_loop: asyncio.AbstractEventLoop | None = None
_wakeup: asyncio.Event | None = None


def wake() -> None:
    """Ask the dispatch loop to run now rather than at its next `dispatch_tick_seconds` tick -
    called whenever something becomes `pending`. Safe from any thread: most producers run on
    APScheduler's thread pool."""
    loop, event = _loop, _wakeup
    if loop is None or event is None:
        return
    try:
        loop.call_soon_threadsafe(event.set)
    except RuntimeError:  # loop already closed, e.g. during shutdown
        pass


async def run_dispatch_loop(session_factory: Callable[[], Session]) -> None:
    """Runs `dispatch_pending` whenever `wake` is called, and at least every
    `dispatch_tick_seconds` as a fallback. Started from app/main.py's lifespan."""
    global _loop, _wakeup
    _loop, _wakeup = asyncio.get_running_loop(), asyncio.Event()
    try:
        while True:
            try:
                await asyncio.wait_for(_wakeup.wait(), timeout=settings.dispatch_tick_seconds)
            except TimeoutError:
                pass
            # Cleared before dispatching, so a wake that lands mid-pass triggers another pass.
            _wakeup.clear()
            try:
                with session_factory() as db:
                    await dispatch_pending(db)
            except Exception:
                logger.exception("Dispatch pass failed")
    finally:
        _loop, _wakeup = None, None


def expire_overdue(db: Session, now: datetime | None = None, user_id: str | None = None) -> int:
    """Give up for good on anything still `pending`/`sent` past its `expires_at` - no more
    sends or nags, and `resend_now` won't revive it (see Notification.expires_at)."""
    now = now or datetime.now(UTC)
    query = db.query(Notification).filter(
        Notification.status.in_([NotificationStatus.pending, NotificationStatus.sent]),
        Notification.expires_at.isnot(None),
        Notification.expires_at <= now,
    )
    if user_id is not None:
        query = query.filter(Notification.user_id == user_id)
    expired = query.update(
        {Notification.status: NotificationStatus.failed, Notification.error: "Expired"},
        synchronize_session=False,
    )
    db.commit()
    return expired


async def dispatch_pending(db: Session, user_id: str | None = None) -> int:
    """Send every `pending` Notification over its user's companion WebSocket, as a `trigger` or
    an `alert` depending on its channel (see `_dispatch_payload`). Returns how many were sent.

    A successful send only means the phone received it - not that the watch showed it, and
    definitely not (for `channel=reminder`) that the wearer acted on it. `requeue_unacked` is
    what handles that gap.

    `user_id` scopes this to one user's notifications - used by `resend_now` so a single watch
    reconnecting doesn't also churn through every other user's pending queue.
    """
    expire_overdue(db, user_id=user_id)
    query = db.query(Notification.user_id).filter(Notification.status == NotificationStatus.pending)
    if user_id is not None:
        query = query.filter(Notification.user_id == user_id)
    user_ids = [row.user_id for row in query.distinct()]

    sent = 0
    for uid in user_ids:
        async with _user_locks[uid]:
            sent += await _dispatch_user(db, uid)
    return sent


def _medication_outstanding(db: Session, user_id: str) -> bool:
    """A medication reminder that's due and not settled yet: waiting to go out, or on the watch
    waiting for its ack. `requeue_unacked` keeps nagging it until `max_send_attempts`, so this
    clears by itself when the wearer acts or the row fails or expires."""
    return (
        db.query(Notification.id)
        .filter(
            Notification.user_id == user_id,
            Notification.channel == NotificationChannel.reminder,
            Notification.kind == ReminderKind.medication,
            Notification.status.in_([NotificationStatus.pending, NotificationStatus.sent]),
        )
        .first()
        is not None
    )


def _displaces_medication(notification: Notification, medication_outstanding: bool) -> bool:
    """The watch holds one reminder at a time, so a new `trigger` silently replaces an unacked
    medication reminder, and the wearer's ack would then be credited to the replacement (see
    app/notify/ack.py). Alerts use a different BLE service and have no ack, so they still go."""
    return (
        medication_outstanding
        and notification.channel == NotificationChannel.reminder
        and notification.kind != ReminderKind.medication
    )


async def _dispatch_user(db: Session, user_id: str) -> int:
    """Medication first, then oldest first, and each row is claimed (`pending` -> `sent`, committed) *before* its send
    awaits: a `delivered`/`ack` the phone answers with can arrive while later rows are still
    going out, and has to find this row already `sent` to be matched to it. The claim is a
    conditional UPDATE, so a row another dispatcher (or a requeue job's thread) moved in the
    meantime is skipped rather than sent twice.

    Other reminders stay `pending` while a medication reminder is outstanding - see
    `_displaces_medication`.

    No connected socket isn't a send attempt: the row just stays `pending` until the phone
    reconnects, instead of burning `max_send_attempts` on ticks that never reached anything.
    """
    pending = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.status == NotificationStatus.pending)
        .order_by(Notification.created_at, Notification.id)
        .all()
    )
    medication_outstanding = _medication_outstanding(db, user_id)
    pending.sort(key=lambda notification: notification.kind != ReminderKind.medication)
    sent = 0
    for notification in pending:
        if not manager.is_connected(user_id):
            break
        if _displaces_medication(notification, medication_outstanding):
            continue
        now = datetime.now(UTC)
        claimed = (
            db.query(Notification)
            .filter(Notification.id == notification.id, Notification.status == NotificationStatus.pending)
            .update(
                {
                    Notification.status: NotificationStatus.sent,
                    Notification.sent_at: now,
                    Notification.send_attempts: Notification.send_attempts + 1,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if not claimed:
            continue
        db.refresh(notification)

        if await manager.send_to_user(user_id, _dispatch_payload(notification)):
            sent += 1
            continue

        # Every socket failed mid-send (and got dropped): undo the claim, unless something
        # already moved the row on.
        gave_up = notification.send_attempts >= settings.max_send_attempts
        db.query(Notification).filter(
            Notification.id == notification.id,
            Notification.status == NotificationStatus.sent,
            Notification.sent_at == now,
        ).update(
            {
                Notification.status: NotificationStatus.failed if gave_up else NotificationStatus.pending,
                Notification.error: "Send failed after max_send_attempts" if gave_up else None,
            },
            synchronize_session=False,
        )
        db.commit()
        db.refresh(notification)
    return sent


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
    # One conditional UPDATE per outcome rather than load-modify-commit: these jobs run on
    # APScheduler's thread pool, concurrently with `record_delivered` on the event loop, and a
    # stale in-memory copy would requeue a row that just got confirmed.
    stale = db.query(Notification).filter(
        Notification.status == NotificationStatus.sent,
        Notification.delivered_at.is_(None),
        Notification.sent_at <= cutoff,
    )
    given_up = stale.filter(Notification.send_attempts >= settings.max_send_attempts).update(
        {
            Notification.status: NotificationStatus.failed,
            Notification.error: "No delivery confirmation received after max_send_attempts",
        },
        synchronize_session=False,
    )
    requeued = stale.filter(Notification.send_attempts < settings.max_send_attempts).update(
        {Notification.status: NotificationStatus.pending}, synchronize_session=False
    )
    db.commit()
    if requeued:
        wake()
    return given_up + requeued


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
    this attempt. Not revived: anything past its `expires_at`, and reminders that failed after
    being delivered but never acked (the wearer already ignored every nag).

    Runs under the user's dispatch lock, so a send already in flight finishes (and is re-sent
    here if still unconfirmed) instead of racing this.
    """
    async with _user_locks[user_id]:
        expire_overdue(db, user_id=user_id)
        # `delivered_at` unset = failed before reaching the watch; set = delivered, nags ignored.
        now = datetime.now(UTC)
        db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.status == NotificationStatus.failed,
            Notification.delivered_at.is_(None),
            or_(Notification.expires_at.is_(None), Notification.expires_at > now),
        ).update(
            {
                Notification.status: NotificationStatus.pending,
                Notification.send_attempts: 0,
                Notification.error: None,
            },
            synchronize_session=False,
        )
        db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.status == NotificationStatus.sent,
            Notification.delivered_at.is_(None),
        ).update({Notification.status: NotificationStatus.pending}, synchronize_session=False)
        db.commit()
        return await _dispatch_user(db, user_id)


def requeue_unacked(db: Session, now: datetime | None = None) -> int:
    """Resend notifications that reached the watch but were never acked within
    `ack_timeout_seconds` - the wearer never snoozed/dismissed it, so nag again.

    Only ever matches `channel=reminder` rows in practice: `record_delivered` moves an `alert`
    straight to `acked` the moment `delivered_at` is set (alerts have no ack step of their own),
    so one never sits around `sent` long enough to hit this query.

    This only runs once a notification is at least `delivered` (see `requeue_undelivered` for the
    earlier, transport-level gap this doesn't cover): resending here is redundant with that faster
    loop for anything that never got delivered in the first place.
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.ack_timeout_seconds)
    # Conditional UPDATEs for the same reason as `requeue_undelivered`.
    stale = db.query(Notification).filter(
        Notification.status == NotificationStatus.sent,
        Notification.delivered_at.isnot(None),
        Notification.sent_at <= cutoff,
    )
    given_up = stale.filter(Notification.send_attempts >= settings.max_send_attempts).update(
        {Notification.status: NotificationStatus.failed, Notification.error: "No ack received after max_send_attempts"},
        synchronize_session=False,
    )
    requeued = stale.filter(Notification.send_attempts < settings.max_send_attempts).update(
        {Notification.status: NotificationStatus.pending, Notification.delivered_at: None},
        synchronize_session=False,
    )
    db.commit()
    if requeued:
        wake()
    return given_up + requeued
