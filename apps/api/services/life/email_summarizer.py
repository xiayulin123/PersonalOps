from __future__ import annotations

import asyncio
import logging

from config import settings
from services.indexer import _openai_client

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = """Write 1-2 short plain sentences summarizing the main point of this email.
Do not use bullet points, labels, or headings (no "From", "Deadline", "What they want").
Keep under 60 words. Use the same language as the email when obvious.

Subject: {subject}
From: {from_line}
Body preview:
{body_preview}
"""


def _preview_summary(subject: str, body_preview: str) -> str:
    text = (body_preview or subject or "").strip()
    if not text:
        return "No preview available."
    sentence = text.split(". ")[0].strip()
    if len(sentence) > 200:
        sentence = sentence[:197] + "..."
    return f"- {sentence}"


def _summarize_openai(subject: str, from_line: str, body_preview: str) -> str:
    prompt = _SUMMARY_PROMPT.format(
        subject=subject or "(no subject)",
        from_line=from_line or "unknown",
        body_preview=(body_preview or "")[:2000],
    )
    response = _openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You write concise email briefs. Plain sentences only.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return (response.choices[0].message.content or "").strip()


async def _summarize_cursor(subject: str, from_line: str, body_preview: str) -> str:
    from cursor_sdk import AgentOptions, LocalAgentOptions
    from cursor_sdk.asyncio import AsyncAgent

    from services.cursor_agent.bridge import get_cursor_client

    prompt = _SUMMARY_PROMPT.format(
        subject=subject or "(no subject)",
        from_line=from_line or "unknown",
        body_preview=(body_preview or "")[:2000],
    )
    client = await get_cursor_client()
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        agent = await AsyncAgent.create(
            AgentOptions(
                api_key=settings.cursor_api_key,
                model=settings.cursor_agent_model,
                local=LocalAgentOptions(cwd=str(Path(tmp))),
            ),
            client=client,
        )
        try:
            run = await agent.send(
                prompt + "\n\nReply with plain sentences only. Do not use tools."
            )
            parts: list[str] = []
            async for message in run.stream():
                msg_type = getattr(message, "type", None)
                if msg_type == "assistant":
                    content = getattr(getattr(message, "message", None), "content", None)
                    if content:
                        for block in content:
                            text = getattr(block, "text", None)
                            if text:
                                parts.append(str(text))
            result = await run.wait()
            if result.result and not parts:
                parts.append(result.result)
        finally:
            await agent.close()
    return "".join(parts).strip()


async def summarize_email(
    *,
    subject: str,
    from_name: str | None,
    from_address: str,
    body_preview: str,
) -> tuple[str, str]:
    """Return (summary_text, engine_label)."""
    from_line = f"{from_name} <{from_address}>" if from_name else from_address

    if settings.cursor_api_key.strip():
        try:
            summary = await asyncio.wait_for(
                _summarize_cursor(subject, from_line, body_preview),
                timeout=90,
            )
            if summary:
                return summary, "cursor"
        except Exception as exc:
            logger.warning("Cursor email summary failed: %s", exc)

    if settings.openai_api_key.strip():
        try:
            summary = await asyncio.to_thread(
                _summarize_openai, subject, from_line, body_preview
            )
            if summary:
                return summary, "openai"
        except Exception as exc:
            logger.warning("OpenAI email summary failed: %s", exc)

    return _preview_summary(subject, body_preview), "preview"
