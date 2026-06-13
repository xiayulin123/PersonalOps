from __future__ import annotations

from pathlib import Path

from services.agent.prompts import build_history_block, build_memory_block
from services.agent.state import HistoryMessage, MemoryItem


def workspace_uploads_dir(workspace_id: str) -> Path:
    from config import settings

    return Path(settings.uploads_dir) / workspace_id


def list_workspace_files(workspace_id: str, *, limit: int = 80) -> list[str]:
    root = workspace_uploads_dir(workspace_id)
    if not root.is_dir():
        return []

    names: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        names.append(rel)
        if len(names) >= limit:
            break
    return names


def build_cursor_agent_prompt(
    question: str,
    *,
    workspace_id: str,
    workspace_type: str,
    memory_items: list[MemoryItem],
    tool_settings: dict,
    history: list[HistoryMessage] | None = None,
) -> str:
    file_search = tool_settings.get("file_search", True)
    web_search = tool_settings.get("web_search", False)
    memory_on = tool_settings.get("memory", True)

    file_lines = list_workspace_files(workspace_id)
    if file_lines:
        files_block = "Files in this workspace (under cwd):\n" + "\n".join(
            f"- {name}" for name in file_lines
        )
    else:
        files_block = "Files in this workspace: none yet."

    rules = [
        "You are PersonalOps, a local workspace assistant.",
        f"Workspace type: {workspace_type}",
        f"Workspace id: {workspace_id}",
        "Your current working directory is this workspace uploads folder.",
        "Answer the user's question using files here when relevant.",
        "Cite filenames when you rely on file content.",
        "If local files lack evidence, say clearly you cannot find enough in workspace files.",
    ]

    if not file_search:
        rules.append("Do NOT read workspace files; answer from general knowledge only.")
    elif not web_search:
        rules.append(
            "Do NOT use web search. Use only local files, list_dir, read, and grep."
        )
    else:
        rules.append(
            "Prefer local files first. Use web search only when workspace files "
            "do not contain the answer."
        )

    if not memory_on:
        memory_block = ""
    else:
        memory_block = build_memory_block(memory_items)

    history_block = build_history_block(history or [])

    sections = [
        "\n".join(rules),
        files_block,
        memory_block,
        history_block,
        f"User question:\n{question.strip()}",
    ]
    return "\n\n".join(section for section in sections if section.strip())
