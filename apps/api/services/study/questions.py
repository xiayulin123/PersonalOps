"""Study practice question DB helpers (S1.2)."""

from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import StudyQuestion, StudyQuestionSet
from schema import StudyQuestionOut, StudyQuestionSetOut, StudyQuestionSetSummaryOut
from services.study.calc_answer import reconcile_calculation_answer
from services.study.serde import loads_json_list, parse_sources


def question_to_out(record: StudyQuestion) -> StudyQuestionOut:
    options_raw = loads_json_list(record.options_json or "[]")
    options = [str(option) for option in options_raw] if options_raw else None
    if options is not None and len(options) == 0:
        options = None

    solution_steps = [str(step) for step in loads_json_list(record.solution_steps_json or "[]")]

    correct_answer = record.correct_answer
    if record.question_type == "calculation" and solution_steps:
        correct_answer, _ = reconcile_calculation_answer(correct_answer, solution_steps)

    return StudyQuestionOut(
        id=record.id,
        set_id=record.set_id,
        workspace_id=record.workspace_id,
        question_type=record.question_type,  # type: ignore[arg-type]
        prompt=record.prompt,
        options=options,
        correct_answer=correct_answer,
        explanation=record.explanation,
        solution_steps=solution_steps,
        sources=parse_sources(record.sources_json),
        topic=record.topic,
        sort_order=record.sort_order,
    )


def question_set_to_out(
    record: StudyQuestionSet,
    *,
    include_questions: bool = True,
) -> StudyQuestionSetOut:
    settings = {}
    try:
        settings = json.loads(record.settings_json or "{}")
    except json.JSONDecodeError:
        settings = {}

    questions = (
        [question_to_out(question) for question in sorted(record.questions, key=lambda q: q.sort_order)]
        if include_questions
        else []
    )

    return StudyQuestionSetOut(
        id=record.id,
        workspace_id=record.workspace_id,
        kind=record.kind,  # type: ignore[arg-type]
        title=record.title,
        settings=settings,
        question_count=len(record.questions) if record.questions else 0,
        created_at=record.created_at,
        questions=questions,
    )


def question_set_summary_out(record: StudyQuestionSet) -> StudyQuestionSetSummaryOut:
    question_count = len(record.questions) if record.questions is not None else 0
    return StudyQuestionSetSummaryOut(
        id=record.id,
        workspace_id=record.workspace_id,
        kind=record.kind,  # type: ignore[arg-type]
        title=record.title,
        question_count=question_count,
        created_at=record.created_at,
    )


async def list_question_sets(
    db: AsyncSession,
    workspace_id: str,
    *,
    kind: str = "practice",
) -> list[StudyQuestionSet]:
    result = await db.execute(
        select(StudyQuestionSet)
        .where(
            StudyQuestionSet.workspace_id == workspace_id,
            StudyQuestionSet.kind == kind,
        )
        .options(selectinload(StudyQuestionSet.questions))
        .order_by(StudyQuestionSet.created_at.desc())
    )
    return list(result.scalars().unique().all())


async def get_question_set_or_404(
    db: AsyncSession,
    workspace_id: str,
    set_id: str,
) -> StudyQuestionSet:
    result = await db.execute(
        select(StudyQuestionSet)
        .where(
            StudyQuestionSet.id == set_id,
            StudyQuestionSet.workspace_id == workspace_id,
        )
        .options(selectinload(StudyQuestionSet.questions))
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Question set not found")
    return record
