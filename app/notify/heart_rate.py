from datetime import datetime, UTC

from sqlalchemy.orm import Session

from app.models import HeartRateReading


def record_heart_rate(db: Session, user_id: str, bpm: int, timestamp_millis: int) -> HeartRateReading:
    """Store an inbound `heart_rate` reading, once.

    The phone keeps each reading until the backend acks it (`heart_rate_ack`) and resends what's
    still pending on every reconnect, so the same reading can arrive more than once - e.g. the
    ack was lost with the socket. A resend is the exact same (timestamp, bpm) pair, which two
    real readings never share, so that pair is the dedupe key: a match returns the existing row.
    """
    recorded_at = datetime.fromtimestamp(timestamp_millis / 1000, tz=UTC)
    existing = (
        db.query(HeartRateReading)
        .filter(
            HeartRateReading.user_id == user_id,
            HeartRateReading.recorded_at == recorded_at,
            HeartRateReading.bpm == bpm,
        )
        .first()
    )
    if existing is not None:
        return existing
    reading = HeartRateReading(user_id=user_id, bpm=bpm, recorded_at=recorded_at)
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading
