"""Workspace access control (tenant isolation)."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, Workspace
from services.deployment import is_cloud_deployment


async def get_accessible_workspace(
    workspace_id: str,
    db: AsyncSession,
    current_user: User | None,
) -> Workspace:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if is_cloud_deployment():
        if current_user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        if workspace.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    if current_user is not None:
        if workspace.user_id is not None and workspace.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    if workspace.user_id is not None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return workspace


async def list_accessible_workspaces(
    db: AsyncSession,
    current_user: User | None,
) -> list[Workspace]:
    if is_cloud_deployment():
        if current_user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        result = await db.execute(
            select(Workspace)
            .where(Workspace.user_id == current_user.id)
            .order_by(Workspace.created_at.desc())
        )
        return list(result.scalars().all())

    if current_user is not None:
        result = await db.execute(
            select(Workspace)
            .where(
                or_(
                    Workspace.user_id == current_user.id,
                    Workspace.user_id.is_(None),
                )
            )
            .order_by(Workspace.created_at.desc())
        )
        return list(result.scalars().all())

    result = await db.execute(
        select(Workspace)
        .where(Workspace.user_id.is_(None))
        .order_by(Workspace.created_at.desc())
    )
    return list(result.scalars().all())
