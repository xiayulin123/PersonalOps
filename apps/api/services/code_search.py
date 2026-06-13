from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

_TIMEOUT_SEC = 5
_DEFAULT_MAX_RESULTS = 20

_RG_IGNORE_GLOBS = (
    "!**/.git/**",
    "!**/node_modules/**",
    "!**/__pycache__/**",
    "!**/.venv/**",
    "!**/dist/**",
    "!**/target/**",
)

_SEARCH_STOPWORDS = frozenset(
    {
        "where",
        "what",
        "which",
        "when",
        "who",
        "how",
        "why",
        "the",
        "and",
        "for",
        "from",
        "with",
        "this",
        "that",
        "defined",
        "definition",
        "find",
        "search",
        "file",
        "files",
        "code",
        "function",
        "class",
        "module",
        "project",
        "about",
        "explain",
        "tell",
        "show",
        "me",
        "is",
        "are",
        "in",
        "on",
        "at",
        "to",
        "of",
        "a",
        "an",
    }
)

_CODE_QUERY_PATTERNS = (
    re.compile(r"\bwhere\s+is\b", re.IGNORECASE),
    re.compile(r"\bdefined\b", re.IGNORECASE),
    re.compile(r"\bfunction\b", re.IGNORECASE),
    re.compile(r"\bclass\b", re.IGNORECASE),
    re.compile(r"\bimport\b", re.IGNORECASE),
    re.compile(r"`[^`]+`"),
    re.compile(r"\b[\w]+Error\b"),
    re.compile(r"\bTraceback\b", re.IGNORECASE),
    re.compile(r"\.py\b"),
    re.compile(r"\.tsx?\b"),
)


def _find_rg_binary() -> str | None:
    configured = settings.ripgrep_bin.strip()
    if configured and os.path.isfile(configured) and os.access(configured, os.X_OK):
        return configured

    for candidate in (
        shutil.which("rg"),
        "/opt/homebrew/bin/rg",
        "/usr/local/bin/rg",
    ):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def is_ripgrep_available() -> bool:
    return _find_rg_binary() is not None


def _workspace_upload_dir(workspace_id: str) -> Path:
    root = Path(settings.uploads_dir).resolve()
    target = (root / workspace_id).resolve()
    if target != root and not str(target).startswith(f"{root}{os.sep}"):
        raise ValueError("Invalid workspace id")
    return target


def extract_code_search_terms(question: str) -> list[str]:
    """Pull likely identifiers / symbols from a code lookup question."""
    trimmed = question.strip()
    if not trimmed:
        return []

    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        cleaned = term.strip().strip("`\"'")
        if not cleaned or cleaned.lower() in _SEARCH_STOPWORDS:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        terms.append(cleaned)

    for match in re.finditer(r"`([^`]+)`", trimmed):
        add(match.group(1))

    for pattern in (
        r"where\s+is\s+[`'\"]?([\w.]+)[`'\"]?\s+defined",
        r"find\s+[`'\"]?([\w.]+)[`'\"]?",
        r"search\s+for\s+[`'\"]?([\w.]+)[`'\"]?",
    ):
        match = re.search(pattern, trimmed, re.IGNORECASE)
        if match:
            add(match.group(1))

    for match in re.finditer(r"\b([A-Za-z_][\w.]*)Error\b", trimmed):
        add(match.group(0))

    for match in re.finditer(r"\b([a-z_][a-z0-9_]{2,})\b", trimmed, re.IGNORECASE):
        add(match.group(1))

    return terms[:5]


def should_run_code_search(question: str) -> bool:
    trimmed = question.strip()
    if not trimmed:
        return False
    if extract_code_search_terms(trimmed):
        return True
    return any(pattern.search(trimmed) for pattern in _CODE_QUERY_PATTERNS)


def _relative_filename(search_dir: Path, file_path: Path) -> str:
    try:
        rel = file_path.relative_to(search_dir)
    except ValueError:
        return file_path.name
    return str(rel).replace(os.sep, "/")


def _python_fallback_search(
    search_dir: Path,
    query: str,
    *,
    max_results: int,
) -> list[dict]:
    if not search_dir.is_dir():
        return []

    hits: list[dict] = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for root, dirnames, filenames in os.walk(search_dir):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {".git", "node_modules", "__pycache__", ".venv", "dist"}
        ]
        for filename in filenames:
            if len(hits) >= max_results:
                return hits
            file_path = Path(root) / filename
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for line_number, line in enumerate(text.splitlines(), start=1):
                if not pattern.search(line):
                    continue
                hits.append(
                    {
                        "filename": _relative_filename(search_dir, file_path),
                        "line_number": line_number,
                        "snippet": line.strip()[:240],
                        "path": str(file_path),
                    }
                )
                if len(hits) >= max_results:
                    return hits

    return hits


def _parse_rg_line(search_dir: Path, line: str) -> dict | None:
    # path:line:content
    parts = line.split(":", 2)
    if len(parts) < 3:
        return None

    file_part, line_number_raw, snippet = parts
    try:
        line_number = int(line_number_raw)
    except ValueError:
        return None

    file_path = Path(file_part)
    if not file_path.is_absolute():
        file_path = search_dir / file_path

    return {
        "filename": _relative_filename(search_dir, file_path),
        "line_number": line_number,
        "snippet": snippet.strip()[:240],
        "path": str(file_path.resolve()),
    }


def search_code(
    workspace_id: str,
    query: str,
    *,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> list[dict]:
    """
    Search code/text files under data/uploads/{workspace_id}/.

    Returns list of {filename, line_number, snippet, path}.
    """
    trimmed = query.strip()
    if not trimmed:
        return []

    max_results = max(1, min(max_results, 50))
    search_dir = _workspace_upload_dir(workspace_id)
    if not search_dir.is_dir():
        return []

    rg_bin = _find_rg_binary()
    if rg_bin:
        rg_args = [
            rg_bin,
            "-n",
            "--no-heading",
            "--color",
            "never",
            "--max-count",
            str(max_results),
        ]
        for pattern in _RG_IGNORE_GLOBS:
            rg_args.extend(["-g", pattern])
        rg_args.extend([trimmed, str(search_dir)])

        try:
            completed = subprocess.run(
                rg_args,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SEC,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("ripgrep timed out for workspace %s", workspace_id)
            return []
        except OSError as exc:
            logger.warning("ripgrep failed: %s", exc)
            return _python_fallback_search(search_dir, trimmed, max_results=max_results)

        if completed.returncode not in (0, 1):
            logger.warning(
                "ripgrep exit %s: %s",
                completed.returncode,
                completed.stderr.strip()[:200],
            )
            return _python_fallback_search(search_dir, trimmed, max_results=max_results)

        hits: list[dict] = []
        for line in completed.stdout.splitlines():
            parsed = _parse_rg_line(search_dir, line)
            if parsed:
                hits.append(parsed)
            if len(hits) >= max_results:
                break
        return hits

    return _python_fallback_search(search_dir, trimmed, max_results=max_results)
