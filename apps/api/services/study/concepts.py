"""Study concept DB helpers (S1.1)."""

from __future__ import annotations

import json

from models import StudyConcept
from schema import StudyConceptOut, StudyConceptSourceOut


def _loads_json_list(raw: str) -> list:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def concept_to_out(record: StudyConcept) -> StudyConceptOut:
    sources_raw = _loads_json_list(record.sources_json)
    sources: list[StudyConceptSourceOut] = []
    for item in sources_raw:
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

    key_points = [str(point) for point in _loads_json_list(record.key_points_json)]
    source_file_ids = [str(fid) for fid in _loads_json_list(record.source_file_ids_json)]

    return StudyConceptOut(
        id=record.id,
        workspace_id=record.workspace_id,
        title=record.title,
        summary=record.summary,
        key_points=key_points,
        example=record.example,
        sources=sources,
        mastery=record.mastery,  # type: ignore[arg-type]
        source_file_ids=source_file_ids,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
