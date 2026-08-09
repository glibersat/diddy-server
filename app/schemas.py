from datetime import datetime

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import AckAction, NotificationStatus, ReminderKind, RuleType


def _validate_ics_url(value: str) -> str:
    """Reject anything but a remote http(s) URL - `fetch_ics_text` used to also accept a local
    file path, which let a self-registered user make the server read arbitrary files off its own
    disk (or hit internal-only URLs). See app/scheduler/ics.py::fetch_ics_text."""
    try:
        scheme = AnyUrl(value).scheme
    except Exception as e:
        raise ValueError("url_or_path must be a valid http(s) URL") from e
    if scheme not in ("http", "https"):
        raise ValueError("url_or_path must be a valid http(s) URL")
    return value


class UserCreate(BaseModel):
    email: str
    timezone: str = "Europe/Paris"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    api_key: str
    timezone: str


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


class AckMessage(BaseModel):
    """Inbound WS message from the companion app, mirroring the BLE Ack characteristic."""

    type: str
    action: str
    snoozedMinutes: int = 0


class DeliveredMessage(BaseModel):
    """Inbound WS message confirming a `trigger`'s BLE write to the watch actually completed -
    distinct from `AckMessage`, which means the wearer acted on it."""

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


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_type: RuleType
    rule_id: str
    scheduled_for: datetime
    title: str
    body: str
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
