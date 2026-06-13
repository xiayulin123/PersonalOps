from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import GitHubLink, Workspace, User
from schema import GitHubLinkOut, GitHubLinkUpdate, GitHubSyncOut
from services.github_client import GitHubClientError
from services.github_sync import save_github_link, sync_github_workspace

router = APIRouter(tags=["github"])

from services.auth.dependencies import get_current_user_for_request
from services.workspace_access import get_accessible_workspace



async def _get_link_or_none(
    workspace_id: str, db: AsyncSession
) -> GitHubLink | None:
    result = await db.execute(
        select(GitHubLink).where(GitHubLink.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


def _to_github_link_out(link: GitHubLink) -> GitHubLinkOut:
    return GitHubLinkOut(
        workspace_id=link.workspace_id,
        repo_url=link.repo_url,
        default_branch=link.default_branch,
        repo_full_name=link.repo_full_name,
        repo_description=link.repo_description,
        last_synced_at=link.last_synced_at,
    )


@router.get("/workspaces/{workspace_id}/github", response_model=GitHubLinkOut | None)
async def get_github_link(workspace_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)):
    await get_accessible_workspace(workspace_id, db, current_user)
    link = await _get_link_or_none(workspace_id, db)
    if link is None:
        return None
    return _to_github_link_out(link)


@router.put("/workspaces/{workspace_id}/github", response_model=GitHubLinkOut)
async def upsert_github_link(
    workspace_id: str,
    body: GitHubLinkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    if workspace.type != "code":
        raise HTTPException(
            status_code=400,
            detail="GitHub linking is only supported for code workspaces",
        )

    repo_url = body.repo_url.strip()
    if not repo_url:
        raise HTTPException(status_code=400, detail="repo_url is required")

    try:
        link = await save_github_link(workspace_id, repo_url, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _to_github_link_out(link)


@router.post(
    "/workspaces/{workspace_id}/github/sync",
    response_model=GitHubSyncOut,
)
async def sync_github_link(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    link = await _get_link_or_none(workspace_id, db)
    if link is None:
        raise HTTPException(status_code=404, detail="GitHub repo is not linked")

    try:
        result = await sync_github_workspace(workspace_id, link, db)
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return GitHubSyncOut(**result)
