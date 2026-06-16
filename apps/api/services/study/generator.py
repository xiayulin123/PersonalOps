"""Study content generation (S1)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import File, StudyConcept, StudyQuestion, StudyQuestionSet, Workspace
from services.openai_runtime import MissingOpenAIKeyError, get_openai_client
from services.study.prompts import (
    CONCEPT_JSON_RETRY_PROMPT,
    CONCEPT_SYSTEM_PROMPT,
    QUESTIONS_JSON_RETRY_PROMPT,
    QUESTIONS_SYSTEM_PROMPT,
    TEST_SYSTEM_PROMPT,
    build_concept_user_prompt,
    build_questions_user_prompt,
)
from services.study.calc_answer import reconcile_calculation_answer
from services.study.schemas import (
    LlmConceptsResponse,
    LlmQuestionsResponse,
    StudyDifficulty,
    StudyLanguage,
    StudyQuestionType,
)
from services.study.type_counts import TYPE_ORDER, active_types, total_requested

logger = logging.getLogger(__name__)

DEFAULT_CONCEPT_MODEL = "gpt-4o-mini"
DEFAULT_QUESTIONS_MODEL = "gpt-4o-mini"
MAX_CONCEPT_COUNT = 30
MAX_PER_TYPE = 10
VALID_QUESTION_TYPES = frozenset({"mcq", "short_answer", "true_false", "calculation"})
CALCULATION_RETRIEVAL_SUFFIX = (
    "worked examples sample problems formulas equations numerical calculation "
    "step-by-step solution units derive solve compute"
)


def _retrieval_topic_hint(
    topic_hint: str | None,
    question_types: set[str],
) -> str | None:
    base = (topic_hint or "").strip()
    if "calculation" in question_types:
        calc_focus = CALCULATION_RETRIEVAL_SUFFIX
        return f"{base} {calc_focus}".strip() if base else calc_focus
    return base or None


def _parse_concepts_json(raw: str) -> LlmConceptsResponse:
    data = json.loads(raw)
    return LlmConceptsResponse.model_validate(data)


def _call_concept_llm(
    *,
    context_block: str,
    count: int,
    topic_hint: str | None,
    title_language: StudyLanguage,
    content_language: StudyLanguage,
    retry: bool = False,
) -> LlmConceptsResponse:
    user_prompt = build_concept_user_prompt(
        context_block=context_block,
        count=count,
        topic_hint=topic_hint,
        title_language=title_language,
        content_language=content_language,
    )
    if retry:
        user_prompt = f"{user_prompt}\n\n{CONCEPT_JSON_RETRY_PROMPT}"

    response = get_openai_client().chat.completions.create(
        model=DEFAULT_CONCEPT_MODEL,
        messages=[
            {"role": "system", "content": CONCEPT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or ""
    return _parse_concepts_json(raw)


def _filename_lookup(files: list[File]) -> dict[str, File]:
    lookup: dict[str, File] = {}
    for file_record in files:
        lookup[file_record.filename] = file_record
        basename = file_record.filename.rsplit("/", 1)[-1]
        lookup[basename] = file_record
    return lookup


def _excerpt_lookup(sources: list[dict]) -> dict[tuple[str, int], str]:
    out: dict[tuple[str, int], str] = {}
    for source in sources:
        filename = str(source.get("filename", ""))
        page = int(source.get("page", 1))
        snippet = str(source.get("snippet", ""))
        key = (filename, page)
        if key not in out and snippet:
            out[key] = snippet
        basename = filename.rsplit("/", 1)[-1]
        base_key = (basename, page)
        if base_key not in out and snippet:
            out[base_key] = snippet
    return out


def _map_source_refs(
    source_refs: list[Any],
    *,
    files_by_name: dict[str, File],
    excerpts: dict[tuple[str, int], str],
) -> list[dict]:
    mapped: list[dict] = []
    for ref in source_refs:
        if hasattr(ref, "model_dump"):
            ref_data = ref.model_dump()
        elif isinstance(ref, dict):
            ref_data = ref
        else:
            continue

        filename = str(ref_data.get("filename", "")).strip()
        page = int(ref_data.get("page", 1))
        file_record = files_by_name.get(filename) or files_by_name.get(
            filename.rsplit("/", 1)[-1]
        )
        excerpt = excerpts.get((filename, page)) or excerpts.get(
            (filename.rsplit("/", 1)[-1], page), ""
        )
        mapped.append(
            {
                "file_id": file_record.id if file_record else "",
                "filename": file_record.filename if file_record else filename,
                "page": page,
                "excerpt": excerpt,
            }
        )
    return mapped


async def generate_concepts(
    db: AsyncSession,
    workspace: Workspace,
    *,
    file_ids: list[str],
    count: int,
    topic_hint: str | None,
    language: StudyLanguage,
    title_language: StudyLanguage | None,
    content_language: StudyLanguage | None,
    ready_files: list[File],
) -> list[StudyConcept]:
    resolved_title_language = title_language or language
    resolved_content_language = content_language or language
    count = max(1, min(count, MAX_CONCEPT_COUNT))

    try:
        context_block, sources, _documents, _metadatas = retrieve_study_context(
            workspace_id=workspace.id,
            file_ids=file_ids,
            topic_hint=topic_hint,
            max_chunks=24,
        )
    except MissingOpenAIKeyError:
        raise
    except Exception as exc:
        logger.exception("Study retrieval failed workspace=%s", workspace.id)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve course content for generation.",
        ) from exc

    if not context_block.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not find enough content in selected files.",
        )

    try:
        parsed = _call_concept_llm(
            context_block=context_block,
            count=count,
            topic_hint=topic_hint,
            title_language=resolved_title_language,
            content_language=resolved_content_language,
        )
    except (json.JSONDecodeError, ValidationError) as first_exc:
        logger.warning("Concept JSON parse failed, retrying once: %s", first_exc)
        try:
            parsed = _call_concept_llm(
                context_block=context_block,
                count=count,
                topic_hint=topic_hint,
                title_language=resolved_title_language,
                content_language=resolved_content_language,
                retry=True,
            )
        except (json.JSONDecodeError, ValidationError) as second_exc:
            raise HTTPException(
                status_code=502,
                detail="Generation failed — try fewer files or add a topic hint.",
            ) from second_exc
    except MissingOpenAIKeyError:
        raise
    except Exception as exc:
        logger.exception("Concept LLM call failed workspace=%s", workspace.id)
        raise HTTPException(
            status_code=502,
            detail="Generation failed — try again in a moment.",
        ) from exc

    if not parsed.concepts:
        raise HTTPException(
            status_code=400,
            detail="Could not find enough content in selected files.",
        )

    files_by_name = _filename_lookup(ready_files)
    excerpts = _excerpt_lookup(sources)

    created: list[StudyConcept] = []
    for item in parsed.concepts[:count]:
        title = item.title.strip()
        if not title:
            continue

        sources_json = _map_source_refs(
            item.source_refs,
            files_by_name=files_by_name,
            excerpts=excerpts,
        )
        record = StudyConcept(
            workspace_id=workspace.id,
            title=title,
            summary=item.summary.strip(),
            key_points_json=json.dumps([point.strip() for point in item.key_points if point.strip()]),
            example=item.example.strip() if item.example else None,
            sources_json=json.dumps(sources_json),
            mastery="learning",
            source_file_ids_json=json.dumps(file_ids),
        )
        db.add(record)
        created.append(record)

    if not created:
        raise HTTPException(
            status_code=400,
            detail="Could not find enough content in selected files.",
        )

    await db.commit()
    for record in created:
        await db.refresh(record)
    return created


async def get_concept_or_404(
    db: AsyncSession,
    workspace_id: str,
    concept_id: str,
) -> StudyConcept:
    record = await db.get(StudyConcept, concept_id)
    if record is None or record.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Concept not found")
    return record


async def list_concepts(db: AsyncSession, workspace_id: str) -> list[StudyConcept]:
    result = await db.execute(
        select(StudyConcept)
        .where(StudyConcept.workspace_id == workspace_id)
        .order_by(StudyConcept.created_at.desc())
    )
    return list(result.scalars().all())


def _parse_questions_json(raw: str) -> LlmQuestionsResponse:
    data = json.loads(raw)
    return LlmQuestionsResponse.model_validate(data)


def _call_questions_llm(
    *,
    context_block: str,
    count: int,
    topic_hint: str | None,
    question_types: list[str],
    difficulty: StudyDifficulty,
    content_language: StudyLanguage,
    retry: bool = False,
    exclude_prompts: list[str] | None = None,
    system_prompt: str = QUESTIONS_SYSTEM_PROMPT,
) -> LlmQuestionsResponse:
    user_prompt = build_questions_user_prompt(
        context_block=context_block,
        count=count,
        topic_hint=topic_hint,
        question_types=question_types,
        difficulty=difficulty,
        content_language=content_language,
        exclude_prompts=exclude_prompts,
    )
    if retry:
        user_prompt = f"{user_prompt}\n\n{QUESTIONS_JSON_RETRY_PROMPT}"

    response = get_openai_client().chat.completions.create(
        model=DEFAULT_QUESTIONS_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.35 if exclude_prompts else 0.25,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or ""
    return _parse_questions_json(raw)


def _normalize_question_type(raw: str, allowed: set[str]) -> str | None:
    normalized = raw.strip().lower().replace("-", "_")
    if normalized in allowed:
        return normalized
    return None


def _normalize_options(question_type: str, options: list[str] | None) -> list[str] | None:
    if question_type in ("short_answer", "calculation"):
        return None
    if question_type == "true_false":
        return ["True", "False"]
    if question_type == "mcq" and options:
        cleaned = [option.strip() for option in options if option.strip()]
        if len(cleaned) == 4:
            return cleaned
    return None


def _normalize_solution_steps(raw_steps: list[str] | None) -> list[str]:
    if not raw_steps:
        return []
    steps: list[str] = []
    for step in raw_steps:
        cleaned = step.strip()
        if cleaned:
            steps.append(cleaned)
    return steps


def _ensure_calculation_steps(correct_answer: str, solution_steps: list[str]) -> list[str]:
    if len(solution_steps) >= 2:
        return solution_steps
    if len(solution_steps) == 1:
        return [*solution_steps, f"Final answer: {correct_answer}"]
    if correct_answer:
        return [
            "Identify the given values and the formula from the course material.",
            f"Final answer: {correct_answer}",
        ]
    return []


def _is_valid_calculation_question(
    *,
    correct_answer: str,
    solution_steps: list[str],
) -> bool:
    if len(correct_answer) < 1:
        return False
    if len(solution_steps) < 2:
        return False
    return True


def _llm_batch_size(target_remaining: int, *, calculation_only: bool) -> int:
    buffer = 4 if calculation_only else 2
    return min(target_remaining + buffer, MAX_PER_TYPE + 5)


def _iter_valid_question_payloads(
    parsed: LlmQuestionsResponse,
    *,
    allowed_types: set[str],
    files_by_name: dict[str, File],
    excerpts: dict[tuple[str, int], str],
    seen_prompts: set[str],
):
    for item in parsed.questions:
        question_type = _normalize_question_type(item.question_type, allowed_types)
        if question_type is None:
            continue

        prompt = item.prompt.strip()
        if not prompt:
            continue

        prompt_key = prompt.casefold()
        if prompt_key in seen_prompts:
            continue

        options = _normalize_options(question_type, item.options)
        if question_type == "mcq" and options is None:
            continue

        correct_answer = item.correct_answer.strip()
        if not correct_answer:
            continue

        solution_steps = _normalize_solution_steps(item.solution_steps)
        if question_type == "calculation":
            solution_steps = _ensure_calculation_steps(correct_answer, solution_steps)
            correct_answer, solution_steps = reconcile_calculation_answer(
                correct_answer,
                solution_steps,
            )
            if not _is_valid_calculation_question(
                correct_answer=correct_answer,
                solution_steps=solution_steps,
            ):
                continue

        sources_json = _map_source_refs(
            item.source_refs,
            files_by_name=files_by_name,
            excerpts=excerpts,
        )

        explanation = item.explanation.strip()
        if question_type == "calculation" and not explanation and solution_steps:
            explanation = "Step-by-step solution based on course formulas and examples."

        seen_prompts.add(prompt_key)
        yield {
            "question_type": question_type,
            "prompt": prompt,
            "options": options,
            "correct_answer": correct_answer,
            "explanation": explanation,
            "solution_steps": solution_steps,
            "sources_json": sources_json,
            "topic": item.topic.strip() if item.topic else None,
        }


async def _generate_questions_for_set(
    db: AsyncSession,
    workspace: Workspace,
    *,
    file_ids: list[str],
    type_counts: dict[str, int],
    kind: str,
    difficulty: StudyDifficulty,
    title: str | None,
    topic_hint: str | None,
    content_language: StudyLanguage,
    ready_files: list[File],
    time_limit_min: int | None = None,
) -> tuple[StudyQuestionSet, dict[str, int]]:
    allowed_types = active_types(type_counts)
    if not allowed_types:
        raise HTTPException(
            status_code=400,
            detail="At least one question type must have count >= 1.",
        )

    try:
        context_block, sources, _documents, _metadatas = retrieve_study_context(
            workspace_id=workspace.id,
            file_ids=file_ids,
            topic_hint=_retrieval_topic_hint(topic_hint, allowed_types),
            max_chunks=28 if "calculation" in allowed_types else 24,
        )
    except MissingOpenAIKeyError:
        raise
    except Exception as exc:
        logger.exception("Study retrieval failed workspace=%s", workspace.id)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve course content for generation.",
        ) from exc

    if not context_block.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not find enough content in selected files.",
        )

    files_by_name = _filename_lookup(ready_files)
    excerpts = _excerpt_lookup(sources)
    types_list = sorted(allowed_types)

    if kind == "test":
        default_title = "Practice test"
    else:
        default_title = "Practice questions"
    set_title = (title or "").strip() or default_title
    settings: dict[str, Any] = {
        "file_ids": file_ids,
        "type_counts": type_counts,
        "question_types": types_list,
        "difficulty": difficulty,
        "topic_hint": topic_hint,
        "content_language": content_language,
    }
    if kind == "test" and time_limit_min is not None:
        settings["time_limit_min"] = time_limit_min

    question_set = StudyQuestionSet(
        workspace_id=workspace.id,
        kind=kind,
        title=set_title,
        settings_json=json.dumps(settings),
    )
    db.add(question_set)
    await db.flush()

    generated_prompts: list[str] = []
    seen_prompt_keys: set[str] = set()
    generated_by_type: dict[str, int] = {key: 0 for key in TYPE_ORDER}
    sort_order = 0
    system_prompt = TEST_SYSTEM_PROMPT if kind == "test" else QUESTIONS_SYSTEM_PROMPT

    for qtype in TYPE_ORDER:
        target = type_counts.get(qtype, 0)
        if target <= 0:
            continue

        created_for_type = 0
        attempt = 0
        max_attempts = 6 if qtype == "calculation" else 4
        single_type = {qtype}

        while created_for_type < target and attempt < max_attempts:
            remaining = target - created_for_type
            batch_size = _llm_batch_size(
                remaining,
                calculation_only=qtype == "calculation",
            )
            try:
                parsed = _call_questions_llm(
                    context_block=context_block,
                    count=batch_size,
                    topic_hint=topic_hint,
                    question_types=[qtype],
                    difficulty=difficulty,
                    content_language=content_language,
                    retry=attempt > 0,
                    exclude_prompts=generated_prompts if generated_prompts else None,
                    system_prompt=system_prompt,
                )
            except (json.JSONDecodeError, ValidationError) as parse_exc:
                if attempt == max_attempts - 1:
                    if sort_order == 0:
                        raise HTTPException(
                            status_code=502,
                            detail="Generation failed — try fewer files or add a topic hint.",
                        ) from parse_exc
                    break
                attempt += 1
                continue
            except MissingOpenAIKeyError:
                raise
            except Exception as exc:
                logger.exception("Question LLM call failed workspace=%s", workspace.id)
                if sort_order == 0:
                    raise HTTPException(
                        status_code=502,
                        detail="Generation failed — try again in a moment.",
                    ) from exc
                break

            for payload in _iter_valid_question_payloads(
                parsed,
                allowed_types=single_type,
                files_by_name=files_by_name,
                excerpts=excerpts,
                seen_prompts=seen_prompt_keys,
            ):
                if created_for_type >= target:
                    break
                generated_prompts.append(payload["prompt"])
                db.add(
                    StudyQuestion(
                        set_id=question_set.id,
                        workspace_id=workspace.id,
                        question_type=payload["question_type"],
                        prompt=payload["prompt"],
                        options_json=json.dumps(payload["options"])
                        if payload["options"]
                        else None,
                        correct_answer=payload["correct_answer"],
                        explanation=payload["explanation"],
                        solution_steps_json=json.dumps(payload["solution_steps"])
                        if payload["solution_steps"]
                        else None,
                        sources_json=json.dumps(payload["sources_json"]),
                        topic=payload["topic"],
                        sort_order=sort_order,
                    )
                )
                created_for_type += 1
                generated_by_type[qtype] += 1
                sort_order += 1

            attempt += 1

    if sort_order == 0:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Could not find enough content in selected files.",
        )

    await db.commit()
    await db.refresh(question_set)
    return question_set, generated_by_type


async def generate_practice_questions(
    db: AsyncSession,
    workspace: Workspace,
    *,
    file_ids: list[str],
    type_counts: dict[str, int],
    difficulty: StudyDifficulty,
    title: str | None,
    topic_hint: str | None,
    content_language: StudyLanguage,
    ready_files: list[File],
) -> tuple[StudyQuestionSet, dict[str, int]]:
    return await _generate_questions_for_set(
        db,
        workspace,
        file_ids=file_ids,
        type_counts=type_counts,
        kind="practice",
        difficulty=difficulty,
        title=title,
        topic_hint=topic_hint,
        content_language=content_language,
        ready_files=ready_files,
    )


async def generate_practice_test(
    db: AsyncSession,
    workspace: Workspace,
    *,
    file_ids: list[str],
    type_counts: dict[str, int],
    difficulty: StudyDifficulty,
    title: str | None,
    topic_hint: str | None,
    content_language: StudyLanguage,
    ready_files: list[File],
    time_limit_min: int,
) -> tuple[StudyQuestionSet, dict[str, int]]:
    return await _generate_questions_for_set(
        db,
        workspace,
        file_ids=file_ids,
        type_counts=type_counts,
        kind="test",
        difficulty=difficulty,
        title=title,
        topic_hint=topic_hint,
        content_language=content_language,
        ready_files=ready_files,
        time_limit_min=time_limit_min,
    )
