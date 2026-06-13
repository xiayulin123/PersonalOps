from __future__ import annotations

import re
import uuid
from pathlib import Path

import httpx

from database import SessionLocal
from models import Conversation, Message
from services.conversation import create_conversation
from services.personalization.prompt_log import (
    get_personalization_stats,
    record_user_prompt,
    resolve_workspace_chat_mode,
)

_QUESTION_RE = re.compile(r"^\d+\.\s+(.+)$")


def parse_questions_from_markdown(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Question file not found: {path}")

    questions: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        if stripped.startswith("**") or stripped.startswith("|"):
            continue
        match = _QUESTION_RE.match(stripped)
        if match:
            questions.append(match.group(1).strip())

    if not questions:
        raise ValueError(f"No numbered questions found in {path}")
    return questions


def resolve_question_file(file_arg: str) -> Path:
    raw = Path(file_arg).expanduser()
    if raw.is_file():
        return raw.resolve()

    api_root = Path(__file__).resolve().parents[2]
    # .../personalops/apps/api -> workspace repo root (AI_Assistant)
    workspace_root = api_root.parent.parent.parent
    for base in (Path.cwd(), api_root, workspace_root, api_root.parent.parent):
        candidate = (base / file_arg).resolve()
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Question file not found: {file_arg}")


async def seed_prompt_logs(
    workspace_id: str,
    questions: list[str],
    *,
    conversation_id: str | None = None,
) -> dict:
    """Write prompts to prompt_log without calling the LLM (fast load test)."""
    written = 0
    async with SessionLocal() as db:
        if conversation_id:
            conversation = await db.get(Conversation, conversation_id)
            if conversation is None or conversation.workspace_id != workspace_id:
                raise ValueError("conversation not found for workspace")
        else:
            conversation = await create_conversation(workspace_id, db)

        chat_mode = await resolve_workspace_chat_mode(db, workspace_id)

        for question in questions:
            text = question.strip()
            if not text:
                continue
            message = Message(
                id=str(uuid.uuid4()),
                conversation_id=conversation.id,
                role="user",
                content=text,
            )
            db.add(message)
            await db.flush()
            row = await record_user_prompt(
                db,
                workspace_id=workspace_id,
                conversation_id=conversation.id,
                message_id=message.id,
                content=text,
                chat_mode=chat_mode,
            )
            if row is not None:
                written += 1

        await db.commit()
        stats = await get_personalization_stats(db, workspace_id)

    return {
        "mode": "seed",
        "written": written,
        "conversation_id": conversation.id,
        "stats": stats,
    }


async def live_chat_prompts(
    workspace_id: str,
    questions: list[str],
    *,
    api_base: str,
    conversation_id: str | None,
    delay_sec: float,
) -> dict:
    """POST each question to /chat (runs full agent — slow, uses API keys)."""
    import asyncio

    api_base = api_base.rstrip("/")
    url = f"{api_base}/workspaces/{workspace_id}/chat"
    sent = 0
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=300.0) as client:
        for index, question in enumerate(questions, start=1):
            payload: dict[str, str] = {"message": question}
            if conversation_id:
                payload["conversation_id"] = conversation_id
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                sent += 1
            except Exception as exc:
                errors.append(f"#{index}: {exc}")
            if delay_sec > 0 and index < len(questions):
                await asyncio.sleep(delay_sec)

    async with SessionLocal() as db:
        stats = await get_personalization_stats(db, workspace_id)

    return {
        "mode": "live",
        "sent": sent,
        "errors": errors,
        "stats": stats,
    }
