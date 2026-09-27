import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AckAction, User
from app.notify.ack import record_ack, record_delivered
from app.notify.connection_manager import manager
from app.notify.dispatcher import resend_now
from app.notify.geofence import check_todo_list_geofences
from app.notify.heart_rate import record_heart_rate
from app.notify.location import record_location
from app.schemas import AckMessage, DeliveredMessage, HeartRateMessage, LocationMessage, WatchReadyMessage

logger = logging.getLogger("diddy.routers.ws")

router = APIRouter()


def _in_session(fn: Callable[..., Any], *args: Any) -> Any:
    """Run a synchronous `fn(db, *args)` with its own session - called via run_in_threadpool,
    so blocking DB work doesn't stall the event loop every other socket (and dispatch) runs on."""
    with SessionLocal() as db:
        return fn(db, *args)


def _user_for_key(db: Session, api_key: str) -> User | None:
    return db.query(User).filter(User.api_key == api_key).first()


def _record_location_and_check_geofences(db: Session, user_id: str, message: LocationMessage) -> None:
    location = record_location(
        db, user_id, message.latitude, message.longitude, message.accuracy, message.timestamp
    )
    check_todo_list_geofences(db, user_id, location)


async def _on_ack(user_id: str, message: AckMessage) -> None:
    await run_in_threadpool(_in_session, record_ack, user_id, AckAction(message.action), message.snoozedMinutes)


async def _on_delivered(user_id: str, message: DeliveredMessage) -> None:  # noqa: ARG001
    await run_in_threadpool(_in_session, record_delivered, user_id)


async def _on_watch_ready(user_id: str, message: WatchReadyMessage) -> None:  # noqa: ARG001
    # Stays on the event loop: resend_now awaits the socket sends itself.
    with SessionLocal() as db:
        await resend_now(db, user_id)


async def _on_heart_rate(user_id: str, message: HeartRateMessage) -> None:
    await run_in_threadpool(_in_session, record_heart_rate, user_id, message.bpm, message.timestamp)


async def _on_location(user_id: str, message: LocationMessage) -> None:
    await run_in_threadpool(_in_session, _record_location_and_check_geofences, user_id, message)


_HANDLERS: dict[str, tuple[type[BaseModel], Callable[[str, Any], Awaitable[None]]]] = {
    "ack": (AckMessage, _on_ack),
    "delivered": (DeliveredMessage, _on_delivered),
    "watch_ready": (WatchReadyMessage, _on_watch_ready),
    "heart_rate": (HeartRateMessage, _on_heart_rate),
    "location": (LocationMessage, _on_location),
}


async def _handle_message(user_id: str, text: str) -> None:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        logger.info("Ignoring non-JSON message from user %s: %r", user_id, text[:200])
        return
    msg_type = raw.get("type") if isinstance(raw, dict) else None
    handler = _HANDLERS.get(msg_type) if isinstance(msg_type, str) else None
    if handler is None:
        logger.info("Ignoring unrecognized message from user %s: %r", user_id, raw)
        return
    schema, on_message = handler
    try:
        message = schema.model_validate(raw)
    except ValidationError:
        logger.info("Ignoring malformed message from user %s: %r", user_id, raw)
        return
    await on_message(user_id, message)


@router.websocket("/ws")
async def companion_ws(
    websocket: WebSocket,
    api_key: str | None = None,
    x_api_key: str | None = Header(default=None),
) -> None:
    """The key is read from the `X-API-Key` header, same as HTTP (app/auth.py), falling back to
    the older `?api_key=` query param - a query string tends to end up in proxy/access logs."""
    key = x_api_key or api_key
    user = await run_in_threadpool(_in_session, _user_for_key, key) if key else None
    if user is None:
        await websocket.close(code=4401, reason="Invalid API key")
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            frame = await websocket.receive()
            if frame["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(frame.get("code", 1000))
            text = frame.get("text")
            if text is None:
                logger.info("Ignoring binary frame from user %s", user.id)
                continue
            # One bad message (or a transient DB error handling it) mustn't cost the phone its
            # connection - it'd have to reconnect, and anything sent meanwhile gets delayed.
            try:
                await _handle_message(user.id, text)
            except Exception:
                logger.exception("Failed to handle message from user %s: %r", user.id, text[:200])
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user.id, websocket)
