"""Auto-scoring for practice tests (S1.3) — MCQ and true/false only."""

from __future__ import annotations

import re

from models import StudyQuestion

AUTO_SCORE_TYPES = frozenset({"mcq", "true_false"})


def normalize_answer(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_mcq_answer(value: str) -> str:
    text = normalize_answer(value)
    if len(text) == 1 and text.isalpha():
        return text
    match = re.match(r"^([a-d])\b", text)
    if match:
        return match.group(1)
    return text


def answers_match(question_type: str, user_answer: str, correct_answer: str) -> bool:
    if question_type == "mcq":
        return normalize_mcq_answer(user_answer) == normalize_mcq_answer(correct_answer)
    if question_type == "true_false":
        user = normalize_answer(user_answer)
        correct = normalize_answer(correct_answer)
        if user in {"t", "true"}:
            user = "true"
        if user in {"f", "false"}:
            user = "false"
        if correct in {"t", "true"}:
            correct = "true"
        if correct in {"f", "false"}:
            correct = "false"
        return user == correct
    return False


def score_attempt(
    questions: list[StudyQuestion],
    answers: dict[str, str],
) -> dict:
    items: list[dict] = []
    auto_correct = 0
    auto_total = 0
    by_topic: dict[str, dict[str, int]] = {}

    for question in sorted(questions, key=lambda q: q.sort_order):
        user_answer = (answers.get(question.id) or "").strip()
        topic = (question.topic or "General").strip() or "General"
        topic_stats = by_topic.setdefault(topic, {"correct": 0, "total": 0})

        if question.question_type in AUTO_SCORE_TYPES:
            auto_total += 1
            topic_stats["total"] += 1
            is_correct = answers_match(
                question.question_type,
                user_answer,
                question.correct_answer,
            )
            if is_correct:
                auto_correct += 1
                topic_stats["correct"] += 1
            items.append(
                {
                    "question_id": question.id,
                    "question_type": question.question_type,
                    "topic": topic,
                    "user_answer": user_answer,
                    "correct_answer": question.correct_answer,
                    "is_correct": is_correct,
                    "auto_scored": True,
                }
            )
        else:
            items.append(
                {
                    "question_id": question.id,
                    "question_type": question.question_type,
                    "topic": topic,
                    "user_answer": user_answer,
                    "correct_answer": question.correct_answer,
                    "is_correct": None,
                    "auto_scored": False,
                }
            )

    return {
        "correct": auto_correct,
        "total": len(questions),
        "auto_scored_correct": auto_correct,
        "auto_scored_total": auto_total,
        "by_topic": by_topic,
        "items": items,
    }
