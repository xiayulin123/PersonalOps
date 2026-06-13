from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Workspace, User
from schema import (
    MemoryOut,
    PersonalizationAdoptAllOut,
    PersonalizationArchiveOut,
    PersonalizationDistillOut,
    PersonalizationSettingsOut,
    PersonalizationSettingsUpdate,
    PersonalizationStatsOut,
    PersonalizationWipeOut,
)
from services.personalization.archive_job import (
    archive_single_workspace,
    run_archive_pass,
)
from services.personalization.distillation import (
    distill_single_workspace,
    run_distillation_pass,
)
from services.personalization.drafts import (
    adopt_all_drafts,
    adopt_draft,
    list_pending_drafts,
    reject_draft,
    wipe_personalization_data,
)
from services.personalization.prompt_log import get_personalization_stats
from services.personalization.settings import (
    personalization_settings_payload,
    update_personalization_settings,
)

router = APIRouter(tags=["personalization"])

from services.auth.dependencies import get_current_user_for_request
from services.workspace_access import get_accessible_workspace



@router.get(
    "/workspaces/{workspace_id}/personalization/stats",
    response_model=PersonalizationStatsOut,
)
async def personalization_stats(
    workspace_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)
):
    await get_accessible_workspace(workspace_id, db, current_user)
    stats = await get_personalization_stats(db, workspace_id)
    return PersonalizationStatsOut(**stats)


@router.get(
    "/workspaces/{workspace_id}/personalization/settings",
    response_model=PersonalizationSettingsOut,
)
async def get_personalization_settings(
    workspace_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    return PersonalizationSettingsOut(**personalization_settings_payload(workspace))


@router.patch(
    "/workspaces/{workspace_id}/personalization/settings",
    response_model=PersonalizationSettingsOut,
)
async def patch_personalization_settings(
    workspace_id: str,
    body: PersonalizationSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    payload = await update_personalization_settings(
        db,
        workspace,
        auto_learn_enabled=body.auto_learn_enabled,
        require_approval=body.require_approval,
    )
    await db.commit()
    return PersonalizationSettingsOut(**payload)


@router.get(
    "/workspaces/{workspace_id}/personalization/drafts",
    response_model=list[MemoryOut],
)
async def list_personalization_drafts(
    workspace_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)
):
    await get_accessible_workspace(workspace_id, db, current_user)
    return await list_pending_drafts(db, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/personalization/drafts/{memory_id}/adopt",
    response_model=MemoryOut,
)
async def adopt_personalization_draft(
    workspace_id: str,
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    memory = await adopt_draft(db, workspace_id, memory_id)
    await db.commit()
    await db.refresh(memory)
    return memory


@router.post(
    "/workspaces/{workspace_id}/personalization/drafts/{memory_id}/reject",
    response_model=MemoryOut,
)
async def reject_personalization_draft(
    workspace_id: str,
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    memory = await reject_draft(db, workspace_id, memory_id)
    await db.commit()
    await db.refresh(memory)
    return memory


@router.post(
    "/workspaces/{workspace_id}/personalization/drafts/adopt-all",
    response_model=PersonalizationAdoptAllOut,
)
async def adopt_all_personalization_drafts(
    workspace_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)
):
    await get_accessible_workspace(workspace_id, db, current_user)
    adopted = await adopt_all_drafts(db, workspace_id)
    await db.commit()
    return PersonalizationAdoptAllOut(adopted=adopted)


@router.delete(
    "/workspaces/{workspace_id}/personalization/data",
    response_model=PersonalizationWipeOut,
)
async def delete_personalization_data(
    workspace_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)
):
    await get_accessible_workspace(workspace_id, db, current_user)
    counts = await wipe_personalization_data(db, workspace_id)
    await db.commit()
    return PersonalizationWipeOut(**counts)


@router.post(
    "/workspaces/{workspace_id}/personalization/archive",
    response_model=PersonalizationArchiveOut,
)
async def archive_workspace_prompts(
    workspace_id: str,
    period_start: date | None = None,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    outcome = await archive_single_workspace(
        workspace_id,
        period_start=period_start,
        force=force,
    )
    return PersonalizationArchiveOut(**outcome)


@router.post("/personalization/archive-all", response_model=list[PersonalizationArchiveOut])
async def archive_all_workspaces(
    period_start: date | None = None,
    force: bool = False,
):
    results = await run_archive_pass(period_start=period_start, force=force)
    return [PersonalizationArchiveOut(**item) for item in results]


@router.post(
    "/workspaces/{workspace_id}/personalization/distill",
    response_model=PersonalizationDistillOut,
)
async def distill_workspace_personalization(
    workspace_id: str,
    period: str = Query("day", pattern="^(day|week)$"),
    period_start: date | None = None,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    outcome = await distill_single_workspace(
        workspace_id,
        period,
        period_start=period_start,
        force=force,
    )
    return PersonalizationDistillOut(**outcome)


@router.post("/personalization/distill-all", response_model=list[PersonalizationDistillOut])
async def distill_all_workspaces(
    period: str = Query("day", pattern="^(day|week)$"),
    period_start: date | None = None,
    force: bool = False,
):
    results = await run_distillation_pass(
        period, period_start=period_start, force=force
    )
    return [PersonalizationDistillOut(**item) for item in results]
