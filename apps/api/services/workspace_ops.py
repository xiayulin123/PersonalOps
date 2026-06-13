from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Workspace
from schema import WORKSPACE_TYPES
from services.folder_watcher import stop_watcher
from services.indexer import _chroma_client

logger = logging.getLogger(__name__)


def validate_workspace_name(name: str) -> str:
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("Workspace name cannot be empty")
    if len(trimmed) > 255:
        raise ValueError("Workspace name must be 255 characters or fewer")
    return trimmed


def validate_workspace_type(workspace_type: str) -> str:
    if workspace_type not in WORKSPACE_TYPES:
        allowed = ", ".join(sorted(WORKSPACE_TYPES))
        raise ValueError(f"type must be one of: {allowed}")
    return workspace_type


def ensure_workspace_uploads_dir(workspace_id: str) -> Path:
    workspace_dir = Path(settings.uploads_dir) / workspace_id
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir


async def create_workspace(
    name: str,
    workspace_type: str,
    db: AsyncSession,
    user_id: str | None = None,
) -> Workspace:
    validated_name = validate_workspace_name(name)
    validated_type = validate_workspace_type(workspace_type)

    workspace = Workspace(
        name=validated_name,
        type=validated_type,
        user_id=user_id,
    )
    db.add(workspace)
    await db.flush()
    ensure_workspace_uploads_dir(workspace.id)
    await db.commit()
    await db.refresh(workspace)
    return workspace


def delete_workspace_storage(workspace_id: str) -> None:
    stop_watcher(workspace_id)

    try:
        client = _chroma_client()
        client.delete_collection(name=f"ws_{workspace_id}")
    except Exception as exc:
        logger.info("Chroma collection missing for workspace %s: %s", workspace_id, exc)

    uploads_path = Path(settings.uploads_dir) / workspace_id
    if uploads_path.exists():
        shutil.rmtree(uploads_path, ignore_errors=True)


async def delete_workspace(workspace_id: str, db: AsyncSession) -> Workspace:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("Workspace not found")

    delete_workspace_storage(workspace_id)
    await db.delete(workspace)
    await db.commit()
    return workspace
