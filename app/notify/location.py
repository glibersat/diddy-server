from datetime import datetime, UTC

from sqlalchemy.orm import Session

from app.models import PhoneLocation


def record_location(
    db: Session,
    user_id: str,
    latitude: float,
    longitude: float,
    accuracy_m: float | None,
    timestamp_millis: int,
) -> PhoneLocation:
    """Store an inbound `location` sample. Every sample is its own row, same convention as
    `record_heart_rate` - no matching/updating against a prior position."""
    location = PhoneLocation(
        user_id=user_id,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy_m,
        recorded_at=datetime.fromtimestamp(timestamp_millis / 1000, tz=UTC),
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location
