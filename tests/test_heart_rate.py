from datetime import datetime, UTC

from app.models import HeartRateReading
from app.notify.heart_rate import record_heart_rate


def test_record_heart_rate_stores_a_reading(db_session, user):
    timestamp_millis = int(datetime(2026, 1, 1, 12, 0, tzinfo=UTC).timestamp() * 1000)

    reading = record_heart_rate(db_session, user.id, 72, timestamp_millis)

    assert reading.user_id == user.id
    assert reading.bpm == 72
    # SQLite round-trips DateTime(timezone=True) as naive - assert on the wall-clock value.
    assert reading.recorded_at.replace(tzinfo=UTC) == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_record_heart_rate_does_not_dedupe(db_session, user):
    """Every reading is its own row - no matching/updating like record_ack does."""
    timestamp_millis = int(datetime(2026, 1, 1, 12, 0, tzinfo=UTC).timestamp() * 1000)

    record_heart_rate(db_session, user.id, 72, timestamp_millis)
    record_heart_rate(db_session, user.id, 74, timestamp_millis)

    assert db_session.query(HeartRateReading).filter(HeartRateReading.user_id == user.id).count() == 2
