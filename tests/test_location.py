from datetime import datetime, UTC

from app.models import PhoneLocation
from app.notify.location import record_location


def test_record_location_stores_a_sample(db_session, user):
    timestamp_millis = int(datetime(2026, 1, 1, 12, 0, tzinfo=UTC).timestamp() * 1000)

    location = record_location(db_session, user.id, 48.8566, 2.3522, 12.5, timestamp_millis)

    assert location.user_id == user.id
    assert location.latitude == 48.8566
    assert location.longitude == 2.3522
    assert location.accuracy_m == 12.5
    # SQLite round-trips DateTime(timezone=True) as naive - assert on the wall-clock value.
    assert location.recorded_at.replace(tzinfo=UTC) == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_record_location_accuracy_is_optional(db_session, user):
    timestamp_millis = int(datetime(2026, 1, 1, 12, 0, tzinfo=UTC).timestamp() * 1000)

    location = record_location(db_session, user.id, 48.8566, 2.3522, None, timestamp_millis)

    assert location.accuracy_m is None


def test_record_location_does_not_dedupe(db_session, user):
    """Every sample is its own row - no matching/updating like record_ack does."""
    timestamp_millis = int(datetime(2026, 1, 1, 12, 0, tzinfo=UTC).timestamp() * 1000)

    record_location(db_session, user.id, 48.8566, 2.3522, None, timestamp_millis)
    record_location(db_session, user.id, 48.8580, 2.3510, None, timestamp_millis)

    assert db_session.query(PhoneLocation).filter(PhoneLocation.user_id == user.id).count() == 2
