from fastapi import APIRouter, Depends

from app import schemas
from app.auth import get_current_user
from app.models import User
from app.notify.alert import send_alert

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("", response_model=schemas.AlertOut)
async def create_alert(
    payload: schemas.AlertCreate, user: User = Depends(get_current_user)
) -> schemas.AlertOut:
    delivered = await send_alert(user, payload.message)
    return schemas.AlertOut(delivered=delivered)
