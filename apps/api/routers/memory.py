from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Memory, Workspace, User
from schema import MemoryCreate, MemoryOut, MemoryUpdate
from services.cursor_agent.memory_sync import sync_cursor_memory_file

router = APIRouter(tags=["memory"])

from services.auth.dependencies import get_current_user_for_request
from services.workspace_access import get_accessible_workspace



async def _get_memory_or_404(
    workspace_id: str, memory_id: str, db: AsyncSession
) -> Memory:
    memory = await db.get(Memory, memory_id)
    if memory is None or memory.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.get("/workspaces/{workspace_id}/memory", response_model=list[MemoryOut])
async def list_memory(workspace_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)):
    await get_accessible_workspace(workspace_id, db, current_user)
    result = await db.execute(
        select(Memory)
        .where(
            Memory.workspace_id == workspace_id,
            Memory.status == "active",
        )
        .order_by(Memory.source.asc(), Memory.kind.asc(), Memory.key.asc())
    )
    return result.scalars().all()


@router.post(
    "/workspaces/{workspace_id}/memory",
    response_model=MemoryOut,
    status_code=201,
)
async def create_memory(
    workspace_id: str,
    body: MemoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)

    key = body.key.strip()
    value = body.value.strip()
    if not key or not value:
        raise HTTPException(status_code=400, detail="key and value cannot be empty")

    existing = await db.execute(
        select(Memory).where(
            Memory.workspace_id == workspace_id,
            Memory.key == key,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Memory key '{key}' already exists in this workspace",
        )

    memory = Memory(
        workspace_id=workspace_id,
        key=key,
        value=value,
        source="manual",
        kind="memory",
        status="active",
        confidence=1.0,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    await sync_cursor_memory_file(workspace_id, db)
    return memory


@router.patch(
    "/workspaces/{workspace_id}/memory/{memory_id}",
    response_model=MemoryOut,
)
async def update_memory(
    workspace_id: str,
    memory_id: str,
    body: MemoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    memory = await _get_memory_or_404(workspace_id, memory_id, db)

    value = body.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="value cannot be empty")

    memory.value = value
    await db.commit()
    await db.refresh(memory)
    await sync_cursor_memory_file(workspace_id, db)
    return memory


@router.delete(
    "/workspaces/{workspace_id}/memory/{memory_id}",
    status_code=204,
)
async def delete_memory(
    workspace_id: str,
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    memory = await _get_memory_or_404(workspace_id, memory_id, db)
    await db.delete(memory)
    await db.commit()
    await sync_cursor_memory_file(workspace_id, db)
