from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DIDDY_")

    database_url: str = "sqlite:///./diddy.db"
    default_timezone: str = "UTC"

    daily_tick_seconds: int = 60
    ics_refresh_seconds: int = 300
    dispatch_tick_seconds: int = 30

    # A `trigger` over the companion WebSocket is fire-and-forget: no delivery guarantee, and no
    # ack unless the wearer explicitly snoozes/dismisses. Resend un-acked notifications so a
    # missed one doesn't just silently vanish.
    ack_timeout_seconds: int = 300
    max_send_attempts: int = 5


settings = Settings()
