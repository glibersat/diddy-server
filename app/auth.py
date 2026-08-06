from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_user(
    api_key: str | None = Security(api_key_header),
    db: Session = Depends(get_db),
) -> User:
    if not api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key header")
    user = db.query(User).filter(User.api_key == api_key).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return user
