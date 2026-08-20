from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.models import User
from app.notify.connection_manager import manager
from app.schemas import RingPhoneOut

router = APIRouter(prefix="/phone", tags=["phone"])


@router.post("/ring", response_model=RingPhoneOut)
async def ring_phone(user: User = Depends(get_current_user)) -> RingPhoneOut:
    """Ask the companion app to ring/vibrate the phone itself (not the watch) - for finding a
    phone that's gone quiet in a bag or under a cushion. Ephemeral, best-effort: unlike
    Notification rows dispatched by app/notify/dispatcher.py, there's nothing useful to retry or
    persist if the phone isn't connected right now."""
    delivered = await manager.send_to_user(user.id, {"type": "ring"})
    return RingPhoneOut(delivered=delivered)
