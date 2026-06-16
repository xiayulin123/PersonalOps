"""Practice test attempt helpers (S1.3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import StudyQuestionSet, StudyTestAttempt
from schema import StudyAttemptResultOut, StudyAttemptStartOut, StudyQuestionTakeOut
from services.study.questions import question_to_out
from services.study.scoring import score_attempt


def question_to_take_out(record) -> StudyQuestionTakeOut:
    options_raw = json.loads(record.options_json or "[]") if record.options_json else []
    options = [str(option) for option in options_raw] if options_raw else None
    if options is not None and len(options) == 0:
        options = None
    return StudyQuestionTakeOut(
        id=record.id,
        set_id=record.set_id,
        question_type=record.question_type,  # type: ignore[arg-type]
        prompt=record.prompt,
        options=options,
        topic=record.topic,
        sort_order=record.sort_order,
    )


async def get_attempt_or_404(
    db: AsyncSession,
    workspace_id: str,
    attempt_id: str,
) -> StudyTestAttempt:
    result = await db.execute(
        select(StudyTestAttempt)
        .where(
            StudyTestAttempt.id == attempt_id,
            StudyTestAttempt.workspace_id == workspace_id,
        )
        .options(
            selectinload(StudyTestAttempt.question_set).selectinload(StudyQuestionSet.questions)
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Test attempt not found")
    return record


async def start_test_attempt(
    db: AsyncSession,
    workspace_id: str,
    question_set: StudyQuestionSet,
) -> StudyAttemptStartOut:
    if question_set.kind != "test":
        raise HTTPException(status_code=400, detail="Only test sets can be attempted.")
    if not question_set.questions:
        raise HTTPException(status_code=400, detail="Test has no questions.")

    settings = {}
    try:
        settings = json.loads(question_set.settings_json or "{}")
    except json.JSONDecodeError:
        settings = {}

    attempt = StudyTestAttempt(
        workspace_id=workspace_id,
        set_id=question_set.id,
        answers_json="{}",
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    questions = sorted(question_set.questions, key=lambda q: q.sort_order)
    return StudyAttemptStartOut(
        attempt_id=attempt.id,
        set_id=question_set.id,
        set_title=question_set.title,
        time_limit_min=int(settings.get("time_limit_min") or 45),
        started_at=attempt.started_at,
        questions=[question_to_take_out(q) for q in questions],
    )


async def submit_test_attempt(
    db: AsyncSession,
    workspace_id: str,
    attempt_id: str,
    answers: dict[str, str],
) -> StudyAttemptResultOut:
    attempt = await get_attempt_or_404(db, workspace_id, attempt_id)
    if attempt.submitted_at is not None:
        raise HTTPException(status_code=400, detail="Attempt already submitted.")

    question_set = attempt.question_set
    if question_set is None:
        raise HTTPException(status_code=404, detail="Question set not found")

    questions = sorted(question_set.questions, key=lambda q: q.sort_order)
    score = score_attempt(questions, answers)

    attempt.answers_json = json.dumps(answers)
    attempt.score_json = json.dumps(score)
    attempt.submitted_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(attempt)

    return attempt_to_result_out(attempt, questions)


def attempt_to_result_out(
    attempt: StudyTestAttempt,
    questions: list,
) -> StudyAttemptResultOut:
    score = {}
    try:
        score = json.loads(attempt.score_json or "{}")
    except json.JSONDecodeError:
        score = {}

    answers = {}
    try:
        answers = json.loads(attempt.answers_json or "{}")
    except json.JSONDecodeError:
        answers = {}

    questions_out = [question_to_out(q) for q in sorted(questions, key=lambda q: q.sort_order)]

    return StudyAttemptResultOut(
        attempt_id=attempt.id,
        set_id=attempt.set_id,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        answers=answers,
        score=score,
        questions=questions_out,
    )
