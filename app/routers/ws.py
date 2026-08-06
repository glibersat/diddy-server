import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.db import SessionLocal
from app.models import AckAction, User
from app.notify.ack import record_ack
from app.notify.connection_manager import manager
from app.schemas import AckMessage

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
            try:
                message = AckMessage.model_validate(raw)
            except ValidationError:
                logger.info("Ignoring malformed message from user %s: %r", user.id, raw)
                continue
            if message.type != "ack":
                continue
            with SessionLocal() as db:
                record_ack(
                    db,
                    user.id,
                    AckAction(message.action),
                    message.snoozedMinutes,
                )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user.id, websocket)
