"""Study workspace routes (S1): review concepts, practice questions, tests."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from schema import (
    StudyAttemptResultOut,
    StudyAttemptStartOut,
    StudyAttemptSubmitIn,
    StudyConceptGenerateIn,
    StudyConceptGenerateOut,
    StudyConceptOut,
    StudyConceptPatchIn,
    StudyQuestionSetOut,
    StudyQuestionSetSummaryOut,
    StudyQuestionsGenerateIn,
    StudyQuestionsGenerateOut,
    StudySourceFileOut,
    StudySourcesOut,
    StudyTestGenerateIn,
    StudyTestGenerateOut,
)
from services.auth.dependencies import get_current_user_for_request
from services.auth.openai_access import (
    http_error_for_missing_openai,
    openai_context_for_workspace,
)
from services.openai_runtime import MissingOpenAIKeyError
from services.study.attempts import (
    attempt_to_result_out,
    get_attempt_or_404,
    start_test_attempt,
    submit_test_attempt,
)
from services.study.concepts import concept_to_out
from services.study.generator import (
    generate_concepts,
    generate_practice_questions,
    generate_practice_test,
    get_concept_or_404,
    list_concepts,
)
from services.study.questions import (
    get_question_set_or_404,
    list_question_sets,
    question_set_summary_out,
    question_set_to_out,
)
from services.study.prerequisites import (
    assert_ready_file_ids,
    assert_study_workspace,
    list_ready_study_files,
)
from services.study.type_counts import total_requested
from services.workspace_access import get_accessible_workspace

router = APIRouter(tags=["study"])


@router.get(
    "/workspaces/{workspace_id}/study/sources",
    response_model=StudySourcesOut,
)
async def list_study_sources(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    """List indexed (ready) course files available for study generation."""
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)

    ready_files = await list_ready_study_files(db, workspace_id)
    items = [
        StudySourceFileOut(
            id=file_record.id,
            filename=file_record.filename,
            chunk_count=file_record.chunk_count,
            status=file_record.status,
        )
        for file_record in ready_files
    ]
    return StudySourcesOut(
        workspace_id=workspace_id,
        ready_count=len(items),
        files=items,
    )


@router.get(
    "/workspaces/{workspace_id}/study/concepts",
    response_model=list[StudyConceptOut],
)
async def get_study_concepts(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)

    records = await list_concepts(db, workspace_id)
    return [concept_to_out(record) for record in records]


@router.post(
    "/workspaces/{workspace_id}/study/concepts/generate",
    response_model=StudyConceptGenerateOut,
)
async def generate_study_concepts(
    workspace_id: str,
    body: StudyConceptGenerateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)
    ready_files = await assert_ready_file_ids(db, workspace_id, body.file_ids)

    try:
        async with openai_context_for_workspace(db, workspace):
            created = await generate_concepts(
                db,
                workspace,
                file_ids=body.file_ids,
                count=body.count,
                topic_hint=body.topic_hint,
                language=body.language,
                title_language=body.title_language,
                content_language=body.content_language,
                ready_files=ready_files,
            )
    except MissingOpenAIKeyError as exc:
        raise http_error_for_missing_openai(exc) from exc

    concepts = [concept_to_out(record) for record in created]
    return StudyConceptGenerateOut(
        generated_count=len(concepts),
        concepts=concepts,
    )


@router.patch(
    "/workspaces/{workspace_id}/study/concepts/{concept_id}",
    response_model=StudyConceptOut,
)
async def patch_study_concept(
    workspace_id: str,
    concept_id: str,
    body: StudyConceptPatchIn,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)

    record = await get_concept_or_404(db, workspace_id, concept_id)

    if body.title is not None:
        record.title = body.title.strip()
    if body.summary is not None:
        record.summary = body.summary
    if body.key_points is not None:
        record.key_points_json = json.dumps(
            [point.strip() for point in body.key_points if point.strip()]
        )
    if body.example is not None:
        record.example = body.example.strip() or None
    if body.mastery is not None:
        record.mastery = body.mastery

    await db.commit()
    await db.refresh(record)
    return concept_to_out(record)


@router.delete(
    "/workspaces/{workspace_id}/study/concepts/{concept_id}",
    status_code=204,
)
async def delete_study_concept(
    workspace_id: str,
    concept_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)

    record = await get_concept_or_404(db, workspace_id, concept_id)
    await db.delete(record)
    await db.commit()
    return Response(status_code=204)


@router.get(
    "/workspaces/{workspace_id}/study/question-sets",
    response_model=list[StudyQuestionSetSummaryOut],
)
async def get_study_question_sets(
    workspace_id: str,
    kind: str = Query(default="practice"),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)

    records = await list_question_sets(db, workspace_id, kind=kind)
    return [question_set_summary_out(record) for record in records]


@router.get(
    "/workspaces/{workspace_id}/study/question-sets/{set_id}",
    response_model=StudyQuestionSetOut,
)
async def get_study_question_set(
    workspace_id: str,
    set_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)

    record = await get_question_set_or_404(db, workspace_id, set_id)
    return question_set_to_out(record)


@router.post(
    "/workspaces/{workspace_id}/study/questions/generate",
    response_model=StudyQuestionsGenerateOut,
)
async def generate_study_questions(
    workspace_id: str,
    body: StudyQuestionsGenerateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)
    ready_files = await assert_ready_file_ids(db, workspace_id, body.file_ids)
    type_counts = body.type_counts.as_dict()

    try:
        async with openai_context_for_workspace(db, workspace):
            question_set, generated_by_type = await generate_practice_questions(
                db,
                workspace,
                file_ids=body.file_ids,
                type_counts=type_counts,
                difficulty=body.difficulty,
                title=body.title,
                topic_hint=body.topic_hint,
                content_language=body.content_language,
                ready_files=ready_files,
            )
    except MissingOpenAIKeyError as exc:
        raise http_error_for_missing_openai(exc) from exc

    record = await get_question_set_or_404(db, workspace_id, question_set.id)
    out = question_set_to_out(record)
    return StudyQuestionsGenerateOut(
        question_set=out,
        requested_count=total_requested(type_counts),
        generated_count=out.question_count,
        type_counts_requested=type_counts,
        type_counts_generated=generated_by_type,
    )


@router.delete(
    "/workspaces/{workspace_id}/study/question-sets/{set_id}",
    status_code=204,
)
async def delete_study_question_set(
    workspace_id: str,
    set_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)

    record = await get_question_set_or_404(db, workspace_id, set_id)
    await db.delete(record)
    await db.commit()
    return Response(status_code=204)


@router.post(
    "/workspaces/{workspace_id}/study/tests/generate",
    response_model=StudyTestGenerateOut,
)
async def generate_study_test(
    workspace_id: str,
    body: StudyTestGenerateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)
    ready_files = await assert_ready_file_ids(db, workspace_id, body.file_ids)
    type_counts = body.type_counts.as_dict()

    try:
        async with openai_context_for_workspace(db, workspace):
            question_set, generated_by_type = await generate_practice_test(
                db,
                workspace,
                file_ids=body.file_ids,
                type_counts=type_counts,
                difficulty=body.difficulty,
                title=body.title,
                topic_hint=body.topic_hint,
                content_language=body.content_language,
                ready_files=ready_files,
                time_limit_min=body.time_limit_min,
            )
    except MissingOpenAIKeyError as exc:
        raise http_error_for_missing_openai(exc) from exc

    record = await get_question_set_or_404(db, workspace_id, question_set.id)
    out = question_set_to_out(record)
    return StudyTestGenerateOut(
        question_set=out,
        requested_count=total_requested(type_counts),
        generated_count=out.question_count,
        type_counts_requested=type_counts,
        type_counts_generated=generated_by_type,
    )


@router.post(
    "/workspaces/{workspace_id}/study/tests/{set_id}/attempts",
    response_model=StudyAttemptStartOut,
)
async def start_study_test_attempt(
    workspace_id: str,
    set_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)

    question_set = await get_question_set_or_404(db, workspace_id, set_id)
    return await start_test_attempt(db, workspace_id, question_set)


@router.post(
    "/workspaces/{workspace_id}/study/tests/attempts/{attempt_id}/submit",
    response_model=StudyAttemptResultOut,
)
async def submit_study_test_attempt(
    workspace_id: str,
    attempt_id: str,
    body: StudyAttemptSubmitIn,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)

    return await submit_test_attempt(
        db,
        workspace_id,
        attempt_id,
        body.answers,
    )


@router.get(
    "/workspaces/{workspace_id}/study/tests/attempts/{attempt_id}",
    response_model=StudyAttemptResultOut,
)
async def get_study_test_attempt(
    workspace_id: str,
    attempt_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_study_workspace(workspace)

    attempt = await get_attempt_or_404(db, workspace_id, attempt_id)
    if attempt.submitted_at is None:
        raise HTTPException(status_code=400, detail="Attempt not submitted yet.")

    question_set = attempt.question_set
    questions = sorted(question_set.questions, key=lambda q: q.sort_order)
    return attempt_to_result_out(attempt, questions)
