import secrets
import uuid
from datetime import datetime, UTC
from enum import Enum

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime


def _uuid() -> str:
    return uuid.uuid4().hex


def _api_key() -> str:
    return secrets.token_urlsafe(32)


def _now() -> datetime:
    return datetime.now(UTC)


class ReminderKind(str, Enum):
    """Matches InfiniTime's ReminderService `kind` byte (icon/accent only)."""

    generic = "generic"
    medication = "medication"
    appointment = "appointment"


class NotificationStatus(str, Enum):
    pending = "pending"  # queued, not yet sent over the companion WebSocket
    sent = "sent"  # delivered to the phone, awaiting an ack (or resend after timeout)
    acked = "acked"  # wearer snoozed or dismissed it on-watch
    failed = "failed"  # no connected device, or gave up after max_send_attempts


class RuleType(str, Enum):
    daily_schedule = "daily_schedule"
    ics_reminder = "ics_reminder"
    manual = "manual"
    daily_digest = "daily_digest"
    place_arrival = "place_arrival"


class AckAction(str, Enum):
    snoozed = "snoozed"
    dismissed = "dismissed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    api_key: Mapped[str] = mapped_column(String, unique=True, index=True, default=_api_key)
    timezone: Mapped[str] = mapped_column(String, default="UTC")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    # Criterion #3: a once-a-day "here's what's coming up" summary, sent at `digest_time`
    # (user's local timezone) if there's at least one appointment that day. See
    # app/scheduler/digest.py.
    digest_enabled: Mapped[bool] = mapped_column(default=False)
    digest_time: Mapped[str | None] = mapped_column(String, nullable=True)  # "HH:MM", 24h, local tz

    daily_schedules: Mapped[list["DailySchedule"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    ics_sources: Mapped[list["IcsSource"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    todo_lists: Mapped[list["TodoList"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class DailySchedule(Base):
    """Criterion #1: fire `message` every day at `time_of_day` (user's timezone)."""

    __tablename__ = "daily_schedules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    time_of_day: Mapped[str] = mapped_column(String)  # "HH:MM", 24h, user's local tz
    weekdays_mask: Mapped[int] = mapped_column(default=0b1111111)  # bit 0 = Monday ... bit 6 = Sunday
    message: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(default=True)

    kind: Mapped[ReminderKind] = mapped_column(String, default=ReminderKind.medication)
    dismissible: Mapped[bool] = mapped_column(default=False)
    snooze_minutes: Mapped[list[int]] = mapped_column(JSON, default=lambda: [5, 15])

    user: Mapped["User"] = relationship(back_populates="daily_schedules")


class IcsSource(Base):
    """Criterion #2: parse an ICS feed and remind `offsets_minutes` before each event.

    `refresh_minutes` only throttles how often the remote feed is re-fetched
    (`cached_ics_text`) - it does NOT gate how often we check for due reminders. Those are two
    different concerns: re-fetching hits someone else's server and should stay infrequent, but
    checking a cached feed against the clock is free and needs to run on every scheduler tick, or
    a reminder can arrive up to `refresh_minutes` late. See app/scheduler/ics.py::run_ics_source_tick.
    """

    __tablename__ = "ics_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    url_or_path: Mapped[str] = mapped_column(String)
    offsets_minutes: Mapped[list[int]] = mapped_column(JSON, default=list)
    refresh_minutes: Mapped[int] = mapped_column(default=15)
    enabled: Mapped[bool] = mapped_column(default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cached_ics_text: Mapped[str | None] = mapped_column(String, nullable=True)

    kind: Mapped[ReminderKind] = mapped_column(String, default=ReminderKind.appointment)
    dismissible: Mapped[bool] = mapped_column(default=True)
    snooze_minutes: Mapped[list[int]] = mapped_column(JSON, default=list)

    user: Mapped["User"] = relationship(back_populates="ics_sources")


class TodoList(Base):
    """A CalDAV calendar's VTODOs, synced periodically (see app/scheduler/todo.py). Optionally
    tied to a place: once set, a `place_arrival` reminder fires the first time the phone's
    reported location comes within `place_radius_m` of it (see app/notify/geofence.py) -
    e.g. a shopping list that reminds you when you're near the store."""

    __tablename__ = "todo_lists"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    caldav_url: Mapped[str] = mapped_column(String)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    password: Mapped[str | None] = mapped_column(String, nullable=True)
    refresh_minutes: Mapped[int] = mapped_column(default=15)
    enabled: Mapped[bool] = mapped_column(default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    place_label: Mapped[str | None] = mapped_column(String, nullable=True)
    place_latitude: Mapped[float | None] = mapped_column(nullable=True)
    place_longitude: Mapped[float | None] = mapped_column(nullable=True)
    place_radius_m: Mapped[int | None] = mapped_column(nullable=True)
    # True while the phone's last-known position was inside place_radius_m. A `place_arrival`
    # reminder fires on the False -> True transition only; staying inside (or never entering)
    # doesn't re-fire, and leaving resets this so the next entry fires again.
    place_inside: Mapped[bool] = mapped_column(default=False)

    kind: Mapped[ReminderKind] = mapped_column(String, default=ReminderKind.generic)
    dismissible: Mapped[bool] = mapped_column(default=True)
    snooze_minutes: Mapped[list[int]] = mapped_column(JSON, default=list)

    user: Mapped["User"] = relationship(back_populates="todo_lists")
    items: Mapped[list["TodoItem"]] = relationship(back_populates="todo_list", cascade="all, delete-orphan")


class TodoItem(Base):
    """One VTODO synced from a TodoList's CalDAV calendar - re-fetched wholesale each sync tick
    and upserted by `uid`, same convention as IcsSource's VEVENTs (see app/scheduler/todo.py)."""

    __tablename__ = "todo_items"
    __table_args__ = (UniqueConstraint("todo_list_id", "uid", name="uq_todo_item_list_uid"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    todo_list_id: Mapped[str] = mapped_column(ForeignKey("todo_lists.id"), index=True)
    uid: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(String)
    due: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed: Mapped[bool] = mapped_column(default=False)

    todo_list: Mapped["TodoList"] = relationship(back_populates="items")


class Notification(Base):
    """Outbox/audit log. `rule_type` + `dedupe_key` is the seam future rule types plug into.

    `status == sent` only means the phone's WebSocket accepted the bytes - the companion app
    drops a `trigger` silently if it isn't currently connected to the watch over BLE. `delivered_at`
    is the stronger signal: the phone's BLE write of the Trigger characteristic actually completed,
    reported back as a `delivered` message. `status` still tracks the wearer's snooze/dismiss `ack`
    on top of that, since delivery to the watch and the wearer acting on it are different things.
    """

    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_notification_dedupe_key"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    rule_type: Mapped[RuleType] = mapped_column(String)
    rule_id: Mapped[str] = mapped_column(String)
    dedupe_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String)

    kind: Mapped[ReminderKind] = mapped_column(String, default=ReminderKind.generic)
    dismissible: Mapped[bool] = mapped_column(default=True)
    snooze_minutes: Mapped[list[int]] = mapped_column(JSON, default=list)

    status: Mapped[NotificationStatus] = mapped_column(String, default=NotificationStatus.pending)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    send_attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    ack_action: Mapped[AckAction | None] = mapped_column(String, nullable=True)
    ack_snoozed_minutes: Mapped[int | None] = mapped_column(nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)


class HeartRateReading(Base):
    """One `heart_rate` message from the companion app - see
    companion-android/docs/backend-protocol.md. Sent for every reading the watch produces, spot
    check or periodic background sample alike, with no de-dup key: the phone doesn't identify
    readings, so a duplicate resend (there isn't one today, but nothing rules it out later) would
    just show up as two rows.
    """

    __tablename__ = "heart_rate_readings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    bpm: Mapped[int] = mapped_column()
    # Stamped by the phone on receipt, not by the watch - see the `timestamp` field note in
    # backend-protocol.md. Indexed since every query against this table is a range scan by time.
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    user: Mapped["User"] = relationship()


class PhoneLocation(Base):
    """One `location` message from the companion app - see
    companion-android/docs/backend-protocol.md. Reported roughly every two minutes while the app
    is running, for "where's my phone" - not a continuous track, just periodic samples."""

    __tablename__ = "phone_locations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    latitude: Mapped[float] = mapped_column()
    longitude: Mapped[float] = mapped_column()
    accuracy_m: Mapped[float | None] = mapped_column(nullable=True)
    # Stamped by the phone on receipt, same convention as HeartRateReading.recorded_at.
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    user: Mapped["User"] = relationship()
