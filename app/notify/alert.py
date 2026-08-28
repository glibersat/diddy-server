"""Fire-and-forget notifications over the companion app's WebSocket, relayed to the watch via
InfiniTime's standard BLE Alert Notification Service - distinct from the custom Reminder/Trigger
pipeline in app/notify/manual.py: no Notification row, no dismiss/snooze options, no ack, no
retry. Mirrors app/routers/phone.py::ring_phone's ephemeral send."""

from app.models import User
from app.notify.connection_manager import manager


async def send_alert(user: User, message: str) -> bool:
    return await manager.send_to_user(user.id, {"type": "alert", "message": message})
