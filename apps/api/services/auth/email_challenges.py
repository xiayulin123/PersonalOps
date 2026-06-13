"""DB-backed email challenges for register verify and password reset."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import AuthEmailChallenge, User
from services.auth.email_codes import generate_numeric_code, hash_code, verify_code
from services.auth.email_sender import is_email_delivery_enabled, send_auth_code_email
from services.auth.passwords import hash_password

PURPOSE_REGISTER = "register_verify"
PURPOSE_RESET = "password_reset"
MAX_ATTEMPTS = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ttl_minutes() -> int:
    return max(5, int(settings.auth_email_code_ttl_minutes))


def _resend_cooldown_sec() -> int:
    return max(30, int(settings.auth_email_resend_cooldown_sec))


def _generic_reset_message() -> str:
    return "If that email is registered, we sent a verification code."


def _generic_register_sent_message() -> str:
    return "Verification code sent. Check your inbox."


async def _invalidate_open_challenges(
    db: AsyncSession,
    *,
    email: str,
    purpose: str,
) -> None:
    await db.execute(
        delete(AuthEmailChallenge).where(
            AuthEmailChallenge.email == email,
            AuthEmailChallenge.purpose == purpose,
            AuthEmailChallenge.used_at.is_(None),
        )
    )


async def _latest_challenge(
    db: AsyncSession,
    *,
    email: str,
    purpose: str,
) -> AuthEmailChallenge | None:
    result = await db.execute(
        select(AuthEmailChallenge)
        .where(
            AuthEmailChallenge.email == email,
            AuthEmailChallenge.purpose == purpose,
            AuthEmailChallenge.used_at.is_(None),
        )
        .order_by(AuthEmailChallenge.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _enforce_resend_cooldown(challenge: AuthEmailChallenge | None) -> None:
    if challenge is None:
        return
    elapsed = (_utcnow() - challenge.created_at).total_seconds()
    if elapsed < _resend_cooldown_sec():
        wait = int(_resend_cooldown_sec() - elapsed)
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {wait}s before requesting another code.",
        )


async def _create_challenge(
    db: AsyncSession,
    *,
    email: str,
    purpose: str,
    password_hash: str | None = None,
) -> tuple[AuthEmailChallenge, str]:
    if not is_email_delivery_enabled():
        raise HTTPException(
            status_code=503,
            detail="Email verification is not configured (set RESEND_API_KEY).",
        )

    await _invalidate_open_challenges(db, email=email, purpose=purpose)
    code = generate_numeric_code()
    challenge = AuthEmailChallenge(
        email=email,
        purpose=purpose,
        code_hash=hash_code(code),
        password_hash=password_hash,
        expires_at=_utcnow() + timedelta(minutes=_ttl_minutes()),
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)
    return challenge, code


async def start_register_challenge(
    db: AsyncSession,
    *,
    email: str,
    password: str,
) -> str:
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    latest = await _latest_challenge(db, email=email, purpose=PURPOSE_REGISTER)
    await _enforce_resend_cooldown(latest)

    _, code = await _create_challenge(
        db,
        email=email,
        purpose=PURPOSE_REGISTER,
        password_hash=password_hash,
    )
    await send_auth_code_email(
        to_email=email,
        code=code,
        purpose=PURPOSE_REGISTER,
    )
    return _generic_register_sent_message()


async def resend_register_challenge(db: AsyncSession, *, email: str) -> str:
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    latest = await _latest_challenge(db, email=email, purpose=PURPOSE_REGISTER)
    if latest is None or latest.password_hash is None:
        raise HTTPException(
            status_code=404,
            detail="No pending registration. Start again from Create account.",
        )
    await _enforce_resend_cooldown(latest)

    _, code = await _create_challenge(
        db,
        email=email,
        purpose=PURPOSE_REGISTER,
        password_hash=latest.password_hash,
    )
    await send_auth_code_email(
        to_email=email,
        code=code,
        purpose=PURPOSE_REGISTER,
    )
    return _generic_register_sent_message()


async def verify_register_challenge(
    db: AsyncSession,
    *,
    email: str,
    code: str,
) -> User:
    challenge = await _latest_challenge(db, email=email, purpose=PURPOSE_REGISTER)
    if challenge is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    if challenge.expires_at < _utcnow():
        raise HTTPException(status_code=400, detail="Code expired. Request a new one.")

    if challenge.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Too many attempts. Request a new code.")

    if not verify_code(code, challenge.code_hash):
        challenge.attempts += 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid verification code")

    if not challenge.password_hash:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        challenge.used_at = _utcnow()
        await db.commit()
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=email,
        password_hash=challenge.password_hash,
        email_verified=True,
    )
    db.add(user)
    challenge.used_at = _utcnow()
    await db.commit()
    await db.refresh(user)
    return user


async def start_password_reset_challenge(db: AsyncSession, *, email: str) -> str:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return _generic_reset_message()

    latest = await _latest_challenge(db, email=email, purpose=PURPOSE_RESET)
    await _enforce_resend_cooldown(latest)

    _, code = await _create_challenge(
        db,
        email=email,
        purpose=PURPOSE_RESET,
        password_hash=None,
    )
    await send_auth_code_email(
        to_email=email,
        code=code,
        purpose=PURPOSE_RESET,
    )
    return _generic_reset_message()


async def reset_password_with_code(
    db: AsyncSession,
    *,
    email: str,
    code: str,
    new_password: str,
) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    challenge = await _latest_challenge(db, email=email, purpose=PURPOSE_RESET)
    if challenge is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    if challenge.expires_at < _utcnow():
        raise HTTPException(status_code=400, detail="Code expired. Request a new one.")

    if challenge.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Too many attempts. Request a new code.")

    if not verify_code(code, challenge.code_hash):
        challenge.attempts += 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid verification code")

    try:
        user.password_hash = hash_password(new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user.email_verified = True
    challenge.used_at = _utcnow()
    await db.commit()
