"""Bootstrap admin user and migrate legacy workspaces + API keys."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import User, Workspace
from services.auth.passwords import hash_password
from services.auth.user_credentials import credentials_from_settings, upsert_user_credential
from services.storage.gcs_app_storage import upload_user_credentials_backup


@dataclass
class BootstrapResult:
    user_id: str
    email: str
    created_user: bool
    workspaces_claimed: int
    credentials_imported: list[str]
    gcs_credentials_uri: str | None
    gcs_error: str | None


async def _get_or_create_admin(
    db: AsyncSession,
    *,
    email: str,
    password: str,
) -> tuple[User, bool]:
    email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user, False

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, True


async def bootstrap_admin(
    db: AsyncSession,
    *,
    email: str | None = None,
    password: str | None = None,
    claim_all_legacy: bool = True,
    sync_gcs: bool = True,
) -> BootstrapResult:
    admin_email = (email or settings.admin_email).strip().lower()
    admin_password = (password or settings.admin_password).strip()
    if not admin_email:
        raise ValueError("ADMIN_EMAIL is required (env or --email)")
    if len(admin_password) < 8:
        raise ValueError("ADMIN_PASSWORD must be at least 8 characters")

    user, created = await _get_or_create_admin(
        db, email=admin_email, password=admin_password
    )

    if claim_all_legacy:
        result = await db.execute(
            update(Workspace)
            .where(Workspace.user_id.is_(None))
            .values(user_id=user.id)
        )
        await db.commit()
        claimed = result.rowcount or 0
    else:
        claimed = 0

    imported: dict[str, str] = {}
    for provider, secret in credentials_from_settings().items():
        await upsert_user_credential(
            db, user_id=user.id, provider=provider, secret=secret
        )
        imported[provider] = secret

    gcs_uri: str | None = None
    gcs_error: str | None = None
    if sync_gcs and imported and settings.gcs_storage_enabled:
        try:
            gcs_uri = upload_user_credentials_backup(
                user.id,
                imported,
                email=user.email,
            )
        except Exception as exc:
            gcs_error = str(exc)

    return BootstrapResult(
        user_id=user.id,
        email=user.email,
        created_user=created,
        workspaces_claimed=claimed,
        credentials_imported=sorted(imported.keys()),
        gcs_credentials_uri=gcs_uri,
        gcs_error=gcs_error,
    )
