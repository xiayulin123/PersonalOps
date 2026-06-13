from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import File, GitHubLink
from routers.files import run_indexing
from services.github_client import (
    GitHubClientError,
    fetch_open_issues_markdown,
    fetch_readme_markdown,
    fetch_repo_metadata,
    parse_github_repo_url,
)

GITHUB_README_FILENAME = "_github_README.md"
GITHUB_ISSUES_FILENAME = "_github_open-issues.md"


async def _upsert_github_file(
    db: AsyncSession,
    workspace_id: str,
    filename: str,
    path: str,
    content: str,
) -> File:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)

    result = await db.execute(
        select(File).where(
            File.workspace_id == workspace_id,
            File.path == path,
        )
    )
    file_record = result.scalar_one_or_none()
    if file_record is None:
        file_record = File(
            workspace_id=workspace_id,
            filename=filename,
            path=path,
            status="pending",
            chunk_count=0,
        )
        db.add(file_record)
    else:
        file_record.status = "pending"
        file_record.chunk_count = 0

    await db.commit()
    await db.refresh(file_record)
    return file_record


async def sync_github_workspace(
    workspace_id: str,
    link: GitHubLink,
    db: AsyncSession,
) -> dict:
    owner, repo = parse_github_repo_url(link.repo_url)
    metadata = fetch_repo_metadata(owner, repo)
    readme = fetch_readme_markdown(owner, repo)
    issues = fetch_open_issues_markdown(owner, repo)

    github_dir = os.path.join(settings.uploads_dir, workspace_id, "_github")
    synced_files: list[dict] = []

    if readme:
        readme_path = os.path.join(github_dir, "README.md")
        file_record = await _upsert_github_file(
            db,
            workspace_id,
            GITHUB_README_FILENAME,
            readme_path,
            readme,
        )
        await run_indexing(file_record.id)
        await db.refresh(file_record)
        synced_files.append(
            {
                "filename": file_record.filename,
                "status": file_record.status,
                "chunk_count": file_record.chunk_count,
            }
        )

    if issues:
        issues_path = os.path.join(github_dir, "OPEN_ISSUES.md")
        file_record = await _upsert_github_file(
            db,
            workspace_id,
            GITHUB_ISSUES_FILENAME,
            issues_path,
            issues,
        )
        await run_indexing(file_record.id)
        await db.refresh(file_record)
        synced_files.append(
            {
                "filename": file_record.filename,
                "status": file_record.status,
                "chunk_count": file_record.chunk_count,
            }
        )

    link.repo_url = metadata["html_url"]
    link.default_branch = metadata["default_branch"]
    link.repo_full_name = metadata["full_name"]
    link.repo_description = metadata["description"]
    link.last_synced_at = datetime.now(timezone.utc).replace(tzinfo=None)

    await db.commit()
    await db.refresh(link)

    return {
        "repo_full_name": link.repo_full_name,
        "default_branch": link.default_branch,
        "last_synced_at": link.last_synced_at,
        "synced_files": synced_files,
        "readme_synced": bool(readme),
        "issues_synced": bool(issues),
    }


async def save_github_link(
    workspace_id: str,
    repo_url: str,
    db: AsyncSession,
) -> GitHubLink:
    owner, repo = parse_github_repo_url(repo_url)
    try:
        metadata = fetch_repo_metadata(owner, repo)
    except GitHubClientError as exc:
        raise ValueError(str(exc)) from exc

    result = await db.execute(
        select(GitHubLink).where(GitHubLink.workspace_id == workspace_id)
    )
    link = result.scalar_one_or_none()
    if link is None:
        link = GitHubLink(workspace_id=workspace_id, repo_url=repo_url)
        db.add(link)

    link.repo_url = metadata["html_url"]
    link.default_branch = metadata["default_branch"]
    link.repo_full_name = metadata["full_name"]
    link.repo_description = metadata["description"]

    await db.commit()
    await db.refresh(link)
    return link
