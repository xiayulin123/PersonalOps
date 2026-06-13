from __future__ import annotations

import json
import re
from typing import Any


def extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Distiller output is not a JSON object")
    return data


def _normalize_items(items: Any, default_kind: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        value = str(item.get("value", "")).strip()
        if not key or not value:
            continue
        try:
            confidence = float(item.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))
        normalized.append(
            {
                "key": key[:255],
                "value": value[:4000],
                "confidence": confidence,
                "kind": default_kind,
            }
        )
    return normalized


def normalize_distill_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "memories": _normalize_items(data.get("memories"), "memory"),
        "rules": _normalize_items(data.get("rules"), "rule"),
        "habits": _normalize_items(data.get("habits"), "habit"),
        "rejected_patterns": [
            str(item).strip()
            for item in (data.get("rejected_patterns") or [])
            if str(item).strip()
        ],
    }
