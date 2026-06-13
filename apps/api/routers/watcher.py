from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import WatchFolder, Workspace, User
from schema import WatchFolderOut, WatchFolderUpdate
from services import folder_watcher

router = APIRouter(tags=["watcher"])

from services.auth.dependencies import get_current_user_for_request
from services.workspace_access import get_accessible_workspace



async def _get_watch_folder_or_none(
    workspace_id: str, db: AsyncSession
) -> WatchFolder | None:
    result = await db.execute(
        select(WatchFolder).where(WatchFolder.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


def _to_watch_folder_out(record: WatchFolder) -> WatchFolderOut:
    return WatchFolderOut(
        workspace_id=record.workspace_id,
        path=record.path,
        enabled=record.enabled,
        last_scan_at=record.last_scan_at,
    )


@router.get("/workspaces/{workspace_id}/watcher", response_model=WatchFolderOut | None)
async def get_watch_folder(workspace_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)):
    await get_accessible_workspace(workspace_id, db, current_user)
    record = await _get_watch_folder_or_none(workspace_id, db)
    if record is None:
        return None
    return _to_watch_folder_out(record)


@router.put("/workspaces/{workspace_id}/watcher", response_model=WatchFolderOut)
async def upsert_watch_folder(
    workspace_id: str,
    body: WatchFolderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)

    watch_path = body.path.strip()
    if not watch_path:
        raise HTTPException(status_code=400, detail="path is required")

    resolved = Path(watch_path).expanduser().resolve()
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="path must be an existing directory")

    record = await _get_watch_folder_or_none(workspace_id, db)
    if record is None:
        record = WatchFolder(
            workspace_id=workspace_id,
            path=str(resolved),
            enabled=body.enabled,
        )
        db.add(record)
    else:
        record.path = str(resolved)
        record.enabled = body.enabled

    await db.commit()
    await db.refresh(record)

    folder_watcher.stop_watcher(workspace_id)
    if record.enabled:
        try:
            folder_watcher.start_watcher(workspace_id, record.path)
            await folder_watcher.scan_watch_folder(workspace_id, record.path)
            await db.refresh(record)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_watch_folder_out(record)


@router.delete("/workspaces/{workspace_id}/watcher", status_code=204)
async def delete_watch_folder(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    record = await _get_watch_folder_or_none(workspace_id, db)
    if record is None:
        raise HTTPException(status_code=404, detail="Watch folder is not configured")

    folder_watcher.stop_watcher(workspace_id)
    await db.delete(record)
    await db.commit()
