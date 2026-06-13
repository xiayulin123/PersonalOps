from __future__ import annotations

import base64
import logging
import re
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

_REPO_URL_PATTERN = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


class GitHubClientError(Exception):
    pass


def parse_github_repo_url(repo_url: str) -> tuple[str, str]:
    cleaned = repo_url.strip()
    match = _REPO_URL_PATTERN.match(cleaned)
    if not match:
        raise GitHubClientError(
            "Invalid GitHub repo URL. Use https://github.com/owner/repo"
        )
    owner = match.group("owner")
    repo = match.group("repo")
    return owner, repo


def _api_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = settings.github_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    response = client.get(
        url,
        headers=_api_headers(),
        params=params,
        timeout=30.0,
    )
    if response.status_code == 404:
        raise GitHubClientError("GitHub repository or resource not found")
    if response.status_code == 403:
        raise GitHubClientError(
            "GitHub API rate limit or forbidden. Set GITHUB_TOKEN for higher limits."
        )
    if response.status_code >= 400:
        raise GitHubClientError(
            f"GitHub API error ({response.status_code}): {response.text[:200]}"
        )
    return response.json()


def fetch_repo_metadata(owner: str, repo: str) -> dict[str, Any]:
    with httpx.Client() as client:
        data = _get_json(client, f"https://api.github.com/repos/{owner}/{repo}")
    return {
        "full_name": data.get("full_name", f"{owner}/{repo}"),
        "description": data.get("description") or "",
        "default_branch": data.get("default_branch") or "main",
        "html_url": data.get("html_url", f"https://github.com/{owner}/{repo}"),
        "stars": int(data.get("stargazers_count") or 0),
        "open_issues": int(data.get("open_issues_count") or 0),
    }


def fetch_readme_markdown(owner: str, repo: str) -> str:
    with httpx.Client() as client:
        try:
            data = _get_json(
                client,
                f"https://api.github.com/repos/{owner}/{repo}/readme",
            )
        except GitHubClientError:
            return ""

    encoding = data.get("encoding", "")
    content = data.get("content", "")
    if not content:
        return ""

    if encoding == "base64":
        try:
            decoded = base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Failed to decode GitHub README: %s", exc)
            return ""
        return decoded.strip()

    return str(content).strip()


def fetch_open_issues_markdown(
    owner: str, repo: str,
    *,
    limit: int = 10,
) -> str:
    with httpx.Client() as client:
        data = _get_json(
            client,
            f"https://api.github.com/repos/{owner}/{repo}/issues",
            params={"state": "open", "per_page": limit, "sort": "updated"},
        )

    if not isinstance(data, list):
        return ""

    lines = [f"# Open issues for {owner}/{repo}", ""]
    issue_count = 0

    for item in data:
        if item.get("pull_request"):
            continue
        issue_count += 1
        number = item.get("number")
        title = item.get("title", "Untitled")
        url = item.get("html_url", "")
        body = (item.get("body") or "").strip()
        lines.append(f"## #{number} {title}")
        if url:
            lines.append(f"URL: {url}")
        if body:
            preview = body[:500] + ("..." if len(body) > 500 else "")
            lines.append("")
            lines.append(preview)
        lines.append("")

    if issue_count == 0:
        lines.append("No open issues found.")

    return "\n".join(lines).strip()
