"""FastAPI auth dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from services.auth.jwt_tokens import decode_access_token
from services.deployment import is_cloud_deployment


async def get_current_user_optional(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_current_user_required(
    current_user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return current_user


async def get_current_user_for_request(
    current_user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User | None:
    """Cloud edition requires login; local desktop allows anonymous legacy access."""
    if is_cloud_deployment() and current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return current_user
