from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User, UserApiCredential
from schema import (
    StorageStatusOut,
    UserCredentialOut,
    UserCredentialUpsertIn,
    UserCredentialsOut,
)
from services.auth.dependencies import get_current_user_required
from services.demo.guards import (
    assert_demo_can_edit_credentials,
    is_demo_user,
    platform_credentials_for_demo,
)
from services.auth.user_credentials import (
    SUPPORTED_PROVIDERS,
    list_user_credentials_masked,
    mask_secret,
    upsert_user_credential,
)
from services.storage.gcs_app_storage import storage_status_for_user

router = APIRouter(prefix="/me", tags=["me"])

_UI_PROVIDERS = ("openai", "tavily")


@router.get("/storage/status", response_model=StorageStatusOut)
async def storage_status(current_user: User = Depends(get_current_user_required)):
    return StorageStatusOut(**storage_status_for_user(current_user.id))


def _provider_label(provider: str) -> str:
    return provider.strip().lower()


@router.get("/credentials", response_model=UserCredentialsOut)
async def list_credentials(
    current_user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    if is_demo_user(current_user):
        platform = platform_credentials_for_demo()
        items: list[UserCredentialOut] = []
        for provider in _UI_PROVIDERS:
            configured = provider in platform
            items.append(
                UserCredentialOut(
                    provider=provider,
                    masked="platform••••" if configured else "",
                    configured=configured,
                    updated_at=None,
                )
            )
        return UserCredentialsOut(items=items)

    configured = {
        item["provider"]: item
        for item in await list_user_credentials_masked(db, user_id=current_user.id)
    }
    items: list[UserCredentialOut] = []
    for provider in _UI_PROVIDERS:
        row = configured.get(provider)
        if row:
            items.append(
                UserCredentialOut(
                    provider=provider,
                    masked=row["masked"],
                    configured=True,
                    updated_at=row["updated_at"],
                )
            )
        else:
            items.append(
                UserCredentialOut(
                    provider=provider,
                    masked="",
                    configured=False,
                    updated_at=None,
                )
            )
    return UserCredentialsOut(items=items)


@router.put("/credentials", response_model=UserCredentialOut)
async def upsert_credential(
    body: UserCredentialUpsertIn,
    current_user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    assert_demo_can_edit_credentials(current_user)
    provider = _provider_label(body.provider)
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    if provider not in _UI_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail="Only openai and tavily can be updated from Settings",
        )

    secret = body.secret.strip()
    if not secret:
        await db.execute(
            delete(UserApiCredential).where(
                UserApiCredential.user_id == current_user.id,
                UserApiCredential.provider == provider,
            )
        )
        await db.commit()
        return UserCredentialOut(
            provider=provider,
            masked="",
            configured=False,
            updated_at=None,
        )

    row = await upsert_user_credential(
        db,
        user_id=current_user.id,
        provider=provider,
        secret=secret,
    )
    plain = secret
    return UserCredentialOut(
        provider=provider,
        masked=mask_secret(secret),
        configured=True,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )
