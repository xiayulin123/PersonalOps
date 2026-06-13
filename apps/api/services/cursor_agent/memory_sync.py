from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Memory
from services.cursor_agent.prompts import workspace_uploads_dir

CURSOR_MEMORY_RULE_REL = ".cursor/rules/personalops-memory.mdc"


def cursor_memory_rule_path(workspace_id: str) -> Path:
    return workspace_uploads_dir(workspace_id) / CURSOR_MEMORY_RULE_REL


def _render_cursor_memory_rule(items: list[Memory]) -> str:
    if not items:
        return ""

    lines = [
        "---",
        "description: PersonalOps workspace memory preferences",
        "alwaysApply: true",
        "---",
        "",
        "# PersonalOps workspace memory",
        "",
        "Follow these preferences when answering in this workspace.",
        "",
    ]
    for item in items:
        label = item.kind if item.kind and item.kind != "memory" else item.key
        lines.append(f"## {label}")
        if item.kind and item.kind != "memory":
            lines.append(f"({item.key})")
        lines.append(item.value.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


async def sync_cursor_memory_file(
    workspace_id: str,
    db: AsyncSession,
) -> str | None:
    """Write SQLite memory rows into Cursor rules under workspace uploads."""
    result = await db.execute(
        select(Memory)
        .where(
            Memory.workspace_id == workspace_id,
            Memory.status == "active",
        )
        .order_by(Memory.kind.asc(), Memory.key.asc())
    )
    items = list(result.scalars().all())
    rule_path = cursor_memory_rule_path(workspace_id)
    rule_path.parent.mkdir(parents=True, exist_ok=True)

    if not items:
        if rule_path.exists():
            rule_path.unlink()
        return None

    content = _render_cursor_memory_rule(items)
    rule_path.write_text(content, encoding="utf-8")
    return str(rule_path)
