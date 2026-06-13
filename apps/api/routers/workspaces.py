from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User, Workspace
from schema import WorkspaceCreate, WorkspaceOut, WorkspaceOverviewOut, WorkspaceUpdate
from services.auth.dependencies import get_current_user_for_request
from services.cursor_agent.memory_sync import sync_cursor_memory_file
from services.deployment import assert_chat_mode_allowed
from services.overview import build_workspace_overview
from services.workspace_access import get_accessible_workspace, list_accessible_workspaces
from services.workspace_ops import create_workspace as create_workspace_record
from services.workspace_ops import delete_workspace as delete_workspace_record

router = APIRouter(tags=["workspaces"])


@router.get("/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspaces = await list_accessible_workspaces(db, current_user)
    return workspaces


@router.post("/workspaces", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    body: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    try:
        return await create_workspace_record(
            body.name,
            body.type,
            db,
            user_id=current_user.id if current_user else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    return await get_accessible_workspace(workspace_id, db, current_user)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: str,
    body: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        workspace.name = name

    if body.chat_mode is not None:
        assert_chat_mode_allowed(body.chat_mode)
        workspace.chat_mode = body.chat_mode

    await db.commit()
    await db.refresh(workspace)

    if workspace.chat_mode == "cursor_agent":
        await sync_cursor_memory_file(workspace_id, db)

    return workspace


@router.get(
    "/workspaces/{workspace_id}/overview",
    response_model=WorkspaceOverviewOut,
)
async def get_workspace_overview(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    return await build_workspace_overview(workspace, db)


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    try:
        await delete_workspace_record(workspace_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
