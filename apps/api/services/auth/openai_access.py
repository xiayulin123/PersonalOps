"""Resolve per-user API keys for chat, indexing, and web search."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, Workspace
from services.auth.user_credentials import (
    SUPPORTED_PROVIDERS,
    get_user_credential_secret,
)
from services.demo.guards import is_demo_user, platform_credentials_for_demo
from services.deployment import is_cloud_deployment
from services.openai_runtime import (
    MISSING_OPENAI_KEY_MESSAGE,
    MissingOpenAIKeyError,
    user_api_keys_context,
)


async def load_user_credentials_map(
    db: AsyncSession,
    user_id: str,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for provider in SUPPORTED_PROVIDERS:
        secret = await get_user_credential_secret(db, user_id=user_id, provider=provider)
        if secret:
            out[provider] = secret
    return out


async def credentials_for_user(db: AsyncSession, user: User | None) -> dict[str, str]:
    if user is None:
        return {}
    if is_demo_user(user):
        return platform_credentials_for_demo()
    return await load_user_credentials_map(db, user.id)


async def credentials_for_workspace_owner(
    db: AsyncSession,
    workspace: Workspace | None,
) -> dict[str, str]:
    if workspace is None or not workspace.user_id:
        return {}
    from models import User

    user = await db.get(User, workspace.user_id)
    if user is not None and is_demo_user(user):
        return platform_credentials_for_demo()
    return await load_user_credentials_map(db, workspace.user_id)


def http_error_for_missing_openai(exc: MissingOpenAIKeyError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc) or MISSING_OPENAI_KEY_MESSAGE)


@asynccontextmanager
async def openai_context_for_user(
    db: AsyncSession,
    user: User | None,
) -> AsyncIterator[None]:
    credentials = await credentials_for_user(db, user)
    if is_cloud_deployment() and user is not None and "openai" not in credentials:
        if not (is_demo_user(user) and platform_credentials_for_demo().get("openai")):
            raise http_error_for_missing_openai(MissingOpenAIKeyError(MISSING_OPENAI_KEY_MESSAGE))
    async with user_api_keys_context(credentials):
        yield


@asynccontextmanager
async def openai_context_for_workspace(
    db: AsyncSession,
    workspace: Workspace | None,
) -> AsyncIterator[None]:
    credentials = await credentials_for_workspace_owner(db, workspace)
    if is_cloud_deployment() and workspace and workspace.user_id:
        if "openai" not in credentials:
            from models import User

            owner = await db.get(User, workspace.user_id)
            has_platform = bool(
                owner is not None
                and is_demo_user(owner)
                and platform_credentials_for_demo().get("openai")
            )
            if not has_platform:
                raise http_error_for_missing_openai(
                    MissingOpenAIKeyError(MISSING_OPENAI_KEY_MESSAGE)
                )
    async with user_api_keys_context(credentials):
        yield
