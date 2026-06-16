"""Shared JSON serialization helpers for study modules."""

from __future__ import annotations

import json

from schema import StudyConceptSourceOut


def loads_json_list(raw: str) -> list:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def loads_json_dict(raw: str) -> dict:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def parse_sources(raw: str) -> list[StudyConceptSourceOut]:
    sources: list[StudyConceptSourceOut] = []
    for item in loads_json_list(raw):
        if not isinstance(item, dict):
            continue
        sources.append(
            StudyConceptSourceOut(
                file_id=str(item.get("file_id", "")),
                filename=str(item.get("filename", "")),
                page=int(item.get("page", 1)),
                excerpt=str(item.get("excerpt", "")),
            )
        )
    return sources
