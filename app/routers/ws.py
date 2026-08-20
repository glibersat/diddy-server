import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.db import SessionLocal
from app.models import AckAction, User
from app.notify.ack import record_ack, record_delivered
from app.notify.connection_manager import manager
from app.notify.dispatcher import resend_now
from app.notify.heart_rate import record_heart_rate
from app.notify.location import record_location
from app.schemas import AckMessage, DeliveredMessage, HeartRateMessage, LocationMessage, WatchReadyMessage

logger = logging.getLogger("diddy.routers.ws")

router = APIRouter()


@router.websocket("/ws")
async def companion_ws(websocket: WebSocket, api_key: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.api_key == api_key).first()
    if user is None:
        await websocket.close(code=4401, reason="Invalid API key")
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type") if isinstance(raw, dict) else None
            if msg_type == "ack":
                try:
                    message = AckMessage.model_validate(raw)
                except ValidationError:
                    logger.info("Ignoring malformed message from user %s: %r", user.id, raw)
                    continue
                with SessionLocal() as db:
                    record_ack(
                        db,
                        user.id,
                        AckAction(message.action),
                        message.snoozedMinutes,
                    )
            elif msg_type == "delivered":
                try:
                    DeliveredMessage.model_validate(raw)
                except ValidationError:
                    logger.info("Ignoring malformed message from user %s: %r", user.id, raw)
                    continue
                with SessionLocal() as db:
                    record_delivered(db, user.id)
            elif msg_type == "watch_ready":
                try:
                    WatchReadyMessage.model_validate(raw)
                except ValidationError:
                    logger.info("Ignoring malformed message from user %s: %r", user.id, raw)
                    continue
                with SessionLocal() as db:
                    await resend_now(db, user.id)
            elif msg_type == "heart_rate":
                try:
                    message = HeartRateMessage.model_validate(raw)
                except ValidationError:
                    logger.info("Ignoring malformed message from user %s: %r", user.id, raw)
                    continue
                with SessionLocal() as db:
                    record_heart_rate(db, user.id, message.bpm, message.timestamp)
            elif msg_type == "location":
                try:
                    message = LocationMessage.model_validate(raw)
                except ValidationError:
                    logger.info("Ignoring malformed message from user %s: %r", user.id, raw)
                    continue
                with SessionLocal() as db:
                    record_location(
                        db, user.id, message.latitude, message.longitude, message.accuracy, message.timestamp
                    )
            else:
                logger.info("Ignoring unrecognized message from user %s: %r", user.id, raw)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user.id, websocket)
