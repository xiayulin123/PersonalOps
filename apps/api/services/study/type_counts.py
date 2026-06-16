"""Per-question-type count validation (1–10 each, Study S1)."""

from __future__ import annotations

from fastapi import HTTPException

from services.study.schemas import StudyQuestionType

MAX_PER_TYPE = 10
MIN_PER_TYPE = 0
TYPE_ORDER: tuple[StudyQuestionType, ...] = (
    "mcq",
    "true_false",
    "short_answer",
    "calculation",
)


def normalize_type_counts(raw: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {key: 0 for key in TYPE_ORDER}
    for key, value in raw.items():
        normalized = key.strip().lower().replace("-", "_")
        if normalized not in out:
            continue
        count = int(value)
        if count < MIN_PER_TYPE or count > MAX_PER_TYPE:
            raise HTTPException(
                status_code=400,
                detail=f"Each question type count must be between 0 and {MAX_PER_TYPE}.",
            )
        out[normalized] = count
    total = sum(out.values())
    if total < 1:
        raise HTTPException(
            status_code=400,
            detail="At least one question type must have count >= 1.",
        )
    return out


def active_types(type_counts: dict[str, int]) -> set[str]:
    return {key for key, value in type_counts.items() if value > 0}


def total_requested(type_counts: dict[str, int]) -> int:
    return sum(type_counts.values())
