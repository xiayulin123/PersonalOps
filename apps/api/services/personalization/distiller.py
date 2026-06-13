from __future__ import annotations

import logging
from typing import Any

from config import settings
from services.personalization.distiller_parse import extract_json, normalize_distill_payload

logger = logging.getLogger(__name__)

_MAX_INPUT_CHARS = 80_000

_DISTILL_SYSTEM = (
    "You analyze a user's chat prompts and extract durable personalization signals. "
    "Return ONLY valid JSON with keys: memories, rules, habits, rejected_patterns. "
    "Each item in memories/rules/habits must have key, value, confidence (0-1). "
    "memories = stable facts; rules = constraints for the assistant; "
    "habits = recurring topics or style preferences. "
    "Do not invent facts. Skip one-off tasks."
)

_DISTILL_USER = """Analyze these user prompts from one {period_label} and extract personalization.

Prompts (redacted):
{prompts}

Return JSON only:
{{
  "memories": [{{"key": "...", "value": "...", "confidence": 0.0}}],
  "rules": [{{"key": "...", "value": "...", "confidence": 0.0}}],
  "habits": [{{"key": "...", "value": "...", "confidence": 0.0}}],
  "rejected_patterns": ["..."]
}}"""


def _sample_prompts(text: str, max_chars: int = _MAX_INPUT_CHARS) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    head = cleaned[: max_chars // 2]
    tail = cleaned[-max_chars // 2 :]
    return f"{head}\n\n...[truncated]...\n\n{tail}"


def distill_prompts_sync(
    prompts_text: str,
    *,
    period_label: str,
    openai_api_key: str,
) -> dict[str, Any]:
    key = openai_api_key.strip()
    if not key:
        raise ValueError("OPENAI_API_KEY is required for prompt distillation")

    sampled = _sample_prompts(prompts_text)
    if not sampled:
        return {
            "memories": [],
            "rules": [],
            "habits": [],
            "rejected_patterns": [],
        }

    from openai import OpenAI

    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model=settings.prompt_distill_model,
        messages=[
            {"role": "system", "content": _DISTILL_SYSTEM},
            {
                "role": "user",
                "content": _DISTILL_USER.format(
                    period_label=period_label,
                    prompts=sampled,
                ),
            },
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    return normalize_distill_payload(extract_json(raw))
