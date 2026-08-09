from datetime import datetime, UTC

from sqlalchemy.orm import Session

from app.models import HeartRateReading


def record_heart_rate(db: Session, user_id: str, bpm: int, timestamp_millis: int) -> HeartRateReading:
    """Store an inbound `heart_rate` reading. Unlike `record_ack`/`record_delivered`, there's no
    matching against existing state - every reading is its own row, not an update to something
    already sent."""
    reading = HeartRateReading(
        user_id=user_id,
        bpm=bpm,
        recorded_at=datetime.fromtimestamp(timestamp_millis / 1000, tz=UTC),
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading
