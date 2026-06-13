"""Per-user API credential storage (Plan B B2 foundation)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import User, UserApiCredential
from services.auth.credential_crypto import decrypt_secret, encrypt_secret

SUPPORTED_PROVIDERS = ("openai", "tavily", "cursor", "github")


def mask_secret(secret: str) -> str:
    secret = secret.strip()
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}...{secret[-4:]}"


async def upsert_user_credential(
    db: AsyncSession,
    *,
    user_id: str,
    provider: str,
    secret: str,
) -> UserApiCredential:
    provider = provider.strip().lower()
    secret = secret.strip()
    if not secret:
        raise ValueError(f"Empty secret for provider {provider}")

    encrypted = encrypt_secret(secret)
    row = await db.get(UserApiCredential, (user_id, provider))
    if row is None:
        row = UserApiCredential(
            user_id=user_id,
            provider=provider,
            encrypted_secret=encrypted,
        )
        db.add(row)
    else:
        row.encrypted_secret = encrypted
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(row)
    return row


async def get_user_credential_secret(
    db: AsyncSession,
    *,
    user_id: str,
    provider: str,
) -> str | None:
    row = await db.get(UserApiCredential, (user_id, provider.strip().lower()))
    if row is None:
        return None
    return decrypt_secret(row.encrypted_secret)


async def list_user_credentials_masked(
    db: AsyncSession,
    *,
    user_id: str,
) -> list[dict[str, str]]:
    result = await db.execute(
        select(UserApiCredential).where(UserApiCredential.user_id == user_id)
    )
    rows = result.scalars().all()
    out: list[dict[str, str]] = []
    for row in rows:
        plain = decrypt_secret(row.encrypted_secret)
        out.append(
            {
                "provider": row.provider,
                "masked": mask_secret(plain),
                "updated_at": row.updated_at.isoformat(),
            }
        )
    return out


def credentials_from_settings() -> dict[str, str]:
    """Import non-empty platform .env keys for admin bootstrap."""
    mapping = {
        "openai": settings.openai_api_key,
        "tavily": settings.tavily_api_key,
        "cursor": settings.cursor_api_key,
        "github": settings.github_token,
    }
    return {k: v.strip() for k, v in mapping.items() if v and v.strip()}
