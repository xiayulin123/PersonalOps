"""Study workspace guards and file readiness checks (S1)."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import File, Workspace
from services.db_ordering import files_recent_first

STUDY_WORKSPACE_TYPE = "study"
FILE_STATUS_READY = "ready"
MAX_STUDY_FILES_PER_GENERATION = 10


def assert_study_workspace(workspace: Workspace) -> None:
    """Return 404 for non-study workspaces (hide feature on other types)."""
    if workspace.type != STUDY_WORKSPACE_TYPE:
        raise HTTPException(status_code=404, detail="Workspace not found")


async def list_ready_study_files(
    db: AsyncSession,
    workspace_id: str,
) -> list[File]:
    result = await db.execute(
        select(File)
        .where(
            File.workspace_id == workspace_id,
            File.status == FILE_STATUS_READY,
        )
        .order_by(files_recent_first())
    )
    return list(result.scalars().all())


async def assert_ready_file_ids(
    db: AsyncSession,
    workspace_id: str,
    file_ids: list[str],
) -> list[File]:
    """Validate selected files are ready; return matching File rows in request order."""
    if not file_ids:
        raise HTTPException(
            status_code=400,
            detail="Select at least one indexed course file.",
        )
    if len(file_ids) > MAX_STUDY_FILES_PER_GENERATION:
        raise HTTPException(
            status_code=400,
            detail=f"Select at most {MAX_STUDY_FILES_PER_GENERATION} files per generation.",
        )

    ready_files = await list_ready_study_files(db, workspace_id)
    ready_by_id = {file_record.id: file_record for file_record in ready_files}

    selected: list[File] = []
    for file_id in file_ids:
        file_record = ready_by_id.get(file_id)
        if file_record is None:
            raise HTTPException(
                status_code=400,
                detail="One or more selected files are not ready for study generation.",
            )
        selected.append(file_record)
    return selected
