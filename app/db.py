from collections.abc import Generator
from datetime import datetime, UTC

from sqlalchemy import create_engine, DateTime, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """`DateTime(timezone=True)` on SQLite: it accepts an aware datetime on write, but silently
    drops the tzinfo on read - every value we ever store is UTC (see `_now`/`datetime.now(UTC)`
    throughout app/models.py), so on read we just re-attach it. Without this, a naive datetime
    serializes with no UTC offset (e.g. "2026-08-12T13:11:13" instead of "...13:11:13+00:00"),
    and JS's `Date` parser treats an offset-less ISO string as *local* time - the frontend then
    displays the raw UTC clock digits mislabeled as the browser's local time.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:  # noqa: ARG002
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
