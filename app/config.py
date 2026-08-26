from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DIDDY_")

    database_url: str = "sqlite:///./diddy.db"
    default_timezone: str = "UTC"

    daily_tick_seconds: int = 60
    ics_refresh_seconds: int = 300
    todo_refresh_seconds: int = 300
    dispatch_tick_seconds: int = 15

    # A `trigger` over the companion WebSocket is fire-and-forget: no delivery guarantee, and no
    # ack unless the wearer explicitly snoozes/dismisses. Resend un-acked notifications so a
    # missed one doesn't just silently vanish.
    ack_timeout_seconds: int = 300
    max_send_attempts: int = 5

    # Separate, much shorter timeout for the `delivered` confirmation (BLE write to the watch
    # actually completed) - a phone that's connected to the backend but not to the watch drops
    # the trigger with no signal at all, so we can't afford to wait as long as ack_timeout_seconds
    # before assuming that happened and resending. The companion app's `watch_ready` message
    # (app/notify/dispatcher.py::resend_now) handles the common case - reconnecting to the watch -
    # near-instantly; this timeout is just the fallback for when that message itself is lost, so
    # it can stay short.
    delivery_timeout_seconds: int = 20


settings = Settings()
