from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from schema import AuthLoginIn, AuthRegisterIn, AuthTokenOut, UserOut
from services.auth.dependencies import get_current_user_required
from services.auth.jwt_tokens import create_access_token
from services.auth.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not _EMAIL_RE.match(normalized):
        raise HTTPException(status_code=400, detail="Invalid email address")
    return normalized


def _user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/register", response_model=AuthTokenOut, status_code=201)
async def register(body: AuthRegisterIn, db: AsyncSession = Depends(get_db)):
    email = _normalize_email(body.email)
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        password_hash = hash_password(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = User(email=email, password_hash=password_hash)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    try:
        token = create_access_token(user_id=user.id, email=user.email)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AuthTokenOut(access_token=token, user=_user_out(user))


@router.post("/login", response_model=AuthTokenOut)
async def login(body: AuthLoginIn, db: AsyncSession = Depends(get_db)):
    email = _normalize_email(body.email)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    try:
        token = create_access_token(user_id=user.id, email=user.email)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AuthTokenOut(access_token=token, user=_user_out(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user_required)):
    return _user_out(current_user)


@router.post("/logout", status_code=204)
async def logout():
    """Client should discard the JWT; no server-side session in B1."""
    return None
