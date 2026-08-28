from datetime import datetime

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import AckAction, NotificationChannel, NotificationStatus, ReminderKind, RuleType


def _validate_http_url(value: str, field_name: str) -> str:
    """Reject anything but a remote http(s) URL - a local file path (or worse, an internal-only
    URL) would let a self-registered user make the server read files it has no business reading.
    See app/scheduler/ics.py::fetch_ics_text and app/scheduler/todo.py::fetch_todo_components."""
    try:
        scheme = AnyUrl(value).scheme
    except Exception as e:
        raise ValueError(f"{field_name} must be a valid http(s) URL") from e
    if scheme not in ("http", "https"):
        raise ValueError(f"{field_name} must be a valid http(s) URL")
    return value


def _validate_ics_url(value: str) -> str:
    return _validate_http_url(value, "url_or_path")


def _validate_caldav_url(value: str) -> str:
    return _validate_http_url(value, "caldav_url")


class UserCreate(BaseModel):
    email: str
    timezone: str = "Europe/Paris"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    api_key: str
    timezone: str
    digest_enabled: bool
    digest_time: str | None


class UserUpdate(BaseModel):
    timezone: str | None = None
    digest_enabled: bool | None = None
    digest_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class _ReminderOptionsMixin(BaseModel):
    """Shared invariant with InfiniTime's ReminderController::Options: a non-dismissible
    reminder with no snooze slots could never be cleared on-watch."""

    dismissible: bool
    snooze_minutes: list[int] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _check_clearable(self) -> "_ReminderOptionsMixin":
        if not self.dismissible and not self.snooze_minutes:
            raise ValueError("dismissible=False requires at least one snooze_minutes entry")
        return self


class DailyScheduleCreate(_ReminderOptionsMixin):
    time_of_day: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekdays_mask: int = 0b1111111
    message: str
    enabled: bool = True
    kind: ReminderKind = ReminderKind.medication
    dismissible: bool = False
    snooze_minutes: list[int] = Field(default_factory=lambda: [5, 15], max_length=3)


class DailyScheduleUpdate(BaseModel):
    time_of_day: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekdays_mask: int | None = None
    message: str | None = None
    enabled: bool | None = None
    kind: ReminderKind | None = None
    dismissible: bool | None = None
    snooze_minutes: list[int] | None = Field(default=None, max_length=3)


class DailyScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    time_of_day: str
    weekdays_mask: int
    message: str
    enabled: bool
    kind: ReminderKind
    dismissible: bool
    snooze_minutes: list[int]


class IcsSourceCreate(_ReminderOptionsMixin):
    url_or_path: str
    offsets_minutes: list[int] = Field(default_factory=lambda: [30, 15])
    refresh_minutes: int = 15
    enabled: bool = True
    kind: ReminderKind = ReminderKind.appointment
    dismissible: bool = True
    snooze_minutes: list[int] = Field(default_factory=list, max_length=3)

    _validate_url = field_validator("url_or_path")(_validate_ics_url)


class IcsSourceUpdate(BaseModel):
    url_or_path: str | None = None
    offsets_minutes: list[int] | None = None
    refresh_minutes: int | None = None
    enabled: bool | None = None
    kind: ReminderKind | None = None
    dismissible: bool | None = None
    snooze_minutes: list[int] | None = Field(default=None, max_length=3)

    @field_validator("url_or_path")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return None if value is None else _validate_ics_url(value)


class IcsSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    url_or_path: str
    offsets_minutes: list[int]
    refresh_minutes: int
    enabled: bool
    last_synced_at: datetime | None
    kind: ReminderKind
    dismissible: bool
    snooze_minutes: list[int]


class _PlaceMixin(BaseModel):
    """A todo list's optional geofence: all three fields are set together or not at all - see
    app/notify/geofence.py. `place_radius_m` is picked in 100m steps (the frontend's map picker
    offers a slider from 100-5000m), matching how imprecise a phone's periodic position sample
    already is."""

    place_label: str | None = None
    place_latitude: float | None = Field(default=None, ge=-90, le=90)
    place_longitude: float | None = Field(default=None, ge=-180, le=180)
    place_radius_m: int | None = Field(default=None, ge=100, le=5000, multiple_of=100)

    @model_validator(mode="after")
    def _check_place_complete(self) -> "_PlaceMixin":
        fields = (self.place_latitude, self.place_longitude, self.place_radius_m)
        if any(f is not None for f in fields) and not all(f is not None for f in fields):
            raise ValueError("place_latitude, place_longitude and place_radius_m must be set together")
        return self


class TodoListCreate(_ReminderOptionsMixin, _PlaceMixin):
    name: str
    caldav_url: str
    username: str | None = None
    password: str | None = None
    refresh_minutes: int = 15
    enabled: bool = True
    kind: ReminderKind = ReminderKind.generic
    dismissible: bool = True
    snooze_minutes: list[int] = Field(default_factory=list, max_length=3)

    _validate_url = field_validator("caldav_url")(_validate_caldav_url)


class TodoListUpdate(BaseModel):
    name: str | None = None
    caldav_url: str | None = None
    username: str | None = None
    password: str | None = None
    refresh_minutes: int | None = None
    enabled: bool | None = None
    kind: ReminderKind | None = None
    dismissible: bool | None = None
    snooze_minutes: list[int] | None = Field(default=None, max_length=3)
    place_label: str | None = None
    place_latitude: float | None = Field(default=None, ge=-90, le=90)
    place_longitude: float | None = Field(default=None, ge=-180, le=180)
    place_radius_m: int | None = Field(default=None, ge=100, le=5000, multiple_of=100)
    clear_place: bool = False  # explicit opt-in to drop an existing place, since None here means "unchanged"

    @field_validator("caldav_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return None if value is None else _validate_caldav_url(value)


class TodoListOut(BaseModel):
    """Deliberately excludes `password` - this goes straight to the frontend and there's no
    reason for it to ever leave the server once saved."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    caldav_url: str
    username: str | None
    refresh_minutes: int
    enabled: bool
    last_synced_at: datetime | None
    place_label: str | None
    place_latitude: float | None
    place_longitude: float | None
    place_radius_m: int | None
    kind: ReminderKind
    dismissible: bool
    snooze_minutes: list[int]


class TodoItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    uid: str
    summary: str
    due: datetime | None
    completed: bool


class AckMessage(BaseModel):
    """Inbound WS message from the companion app, mirroring the BLE Ack characteristic."""

    type: str
    action: str
    snoozedMinutes: int = 0


class DeliveredMessage(BaseModel):
    """Inbound WS message confirming a `trigger`'s BLE write to the watch actually completed -
    distinct from `AckMessage`, which means the wearer acted on it."""

    type: str


class WatchReadyMessage(BaseModel):
    """Inbound WS message: the phone's BLE connection to the watch just became ready (including
    a reconnect after being out of range/off). Prompts an immediate retry of anything `sent` but
    never `delivered`, instead of waiting for `requeue_undelivered`'s timeout."""

    type: str


class HeartRateMessage(BaseModel):
    """Inbound WS message, one per reading the watch produces - see
    companion-android/docs/backend-protocol.md. `timestamp` is milliseconds since epoch, stamped
    by the phone on receipt."""

    type: str
    bpm: int
    timestamp: int


class HeartRateReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bpm: int
    recorded_at: datetime


class LocationMessage(BaseModel):
    """Inbound WS message, one per periodic position sample the companion app reports - see
    companion-android/docs/backend-protocol.md. `timestamp` is milliseconds since epoch, stamped
    by the phone on receipt, same convention as `HeartRateMessage`."""

    type: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: float | None = None
    timestamp: int


class PhoneLocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    latitude: float
    longitude: float
    accuracy_m: float | None
    recorded_at: datetime


class NextReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_type: RuleType
    title: str
    body: str
    kind: ReminderKind
    scheduled_for: datetime


class RingPhoneOut(BaseModel):
    delivered: bool


class AlertCreate(BaseModel):
    """A light, fire-and-forget notification sent over the BLE-standard Alert Notification
    Service, not the custom Reminder/Trigger pipeline - no dismiss/snooze options, no ack, no
    persistence or retry."""

    message: str = Field(max_length=100)


class AlertOut(BaseModel):
    delivered: bool


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_type: RuleType
    rule_id: str
    scheduled_for: datetime
    title: str
    body: str
    channel: NotificationChannel
    kind: ReminderKind
    dismissible: bool
    snooze_minutes: list[int]
    status: NotificationStatus
    sent_at: datetime | None
    delivered_at: datetime | None
    send_attempts: int
    error: str | None
    ack_action: AckAction | None
    ack_snoozed_minutes: int | None
    acked_at: datetime | None
