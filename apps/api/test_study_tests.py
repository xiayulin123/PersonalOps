"""S1.3 study practice test tests."""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-study-tests")
os.environ.setdefault("DEPLOYMENT_MODE", "local")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-study-tests")
os.environ["RESEND_API_KEY"] = ""

from main import app  # noqa: E402
from models import File  # noqa: E402
from services.study.scoring import answers_match, score_attempt  # noqa: E402


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def _register(client: AsyncClient, email: str, password: str = "password123") -> str:
    with patch("routers.auth.is_email_delivery_enabled", return_value=False):
        res = await client.post(
            "/auth/register",
            json={"email": email, "password": password},
        )
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


async def _create_study_workspace(client: AsyncClient, headers: dict) -> str:
    ws = await client.post(
        "/workspaces",
        headers=headers,
        json={"name": "CSC369", "type": "study"},
    )
    assert ws.status_code == 201
    return ws.json()["id"]


async def _seed_ready_file(workspace_id: str, filename: str = "lec07.pdf") -> str:
    from database import SessionLocal

    async with SessionLocal() as db:
        file_record = File(
            workspace_id=workspace_id,
            filename=filename,
            path=f"/tmp/{workspace_id}/{filename}",
            status="ready",
            chunk_count=8,
        )
        db.add(file_record)
        await db.commit()
        await db.refresh(file_record)
        return file_record.id


def _question(question_id: str, question_type: str, correct: str, sort_order: int = 0):
    return SimpleNamespace(
        id=question_id,
        question_type=question_type,
        correct_answer=correct,
        topic="Topic",
        sort_order=sort_order,
    )


def test_answers_match_mcq_letter_and_text():
    assert answers_match("mcq", "b", "B")
    assert answers_match("mcq", "b) Hold and wait", "Hold and wait")
    assert not answers_match("mcq", "a", "B")


def test_answers_match_true_false_variants():
    assert answers_match("true_false", "True", "true")
    assert answers_match("true_false", "f", "False")
    assert not answers_match("true_false", "True", "False")


def test_reconcile_calculation_answer_prefers_steps():
    from services.study.calc_answer import reconcile_calculation_answer

    steps = [
        "Substitute values into Bayes formula.",
        "Final answer: P(approved|married, income=45) = 0.20 / 0.28 = 0.7143",
    ]
    reconciled, _ = reconcile_calculation_answer("0.013", steps)
    assert "0.7143" in reconciled


def test_score_attempt_auto_scores_mcq_and_tf_only():
    questions = [
        _question("q1", "mcq", "B", 0),
        _question("q2", "true_false", "False", 1),
        _question("q3", "short_answer", "mutex", 2),
    ]
    score = score_attempt(
        questions,
        {"q1": "B", "q2": "True", "q3": "mutex"},
    )
    assert score["auto_scored_correct"] == 1
    assert score["auto_scored_total"] == 2
    assert score["total"] == 3
    assert score["items"][2]["auto_scored"] is False
    assert score["items"][2]["is_correct"] is None


@pytest.mark.asyncio
async def test_generate_test_and_submit_attempt(client):
    email = _unique_email("study-test-flow")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)
    file_id = await _seed_ready_file(workspace_id)

    from services.study.schemas import LlmQuestionItem, LlmQuestionsResponse, LlmSourceRef

    mcq = LlmQuestionItem(
        question_type="mcq",
        prompt="Which is NOT a deadlock condition?",
        options=["Mutual exclusion", "Preemption", "Hold and wait", "Circular wait"],
        correct_answer="Preemption",
        explanation="Preemption prevents deadlock.",
        topic="Deadlock",
        source_refs=[LlmSourceRef(filename="lec07.pdf", page=3)],
    )
    tf = LlmQuestionItem(
        question_type="true_false",
        prompt="Deadlock is always preventable.",
        options=["True", "False"],
        correct_answer="False",
        explanation="Not always.",
        topic="Deadlock",
        source_refs=[],
    )

    call_count = {"n": 0}

    def mock_llm(**_kwargs):
        call_count["n"] += 1
        item = mcq if call_count["n"] == 1 else tf
        return LlmQuestionsResponse(questions=[item])

    with (
        patch(
            "services.study.generator.retrieve_study_context",
            return_value=("context", [], [], []),
        ),
        patch("services.study.generator._call_questions_llm", side_effect=mock_llm),
    ):
        created = await client.post(
            f"/workspaces/{workspace_id}/study/tests/generate",
            headers=headers,
            json={
                "file_ids": [file_id],
                "type_counts": {
                    "mcq": 1,
                    "short_answer": 0,
                    "calculation": 0,
                    "true_false": 1,
                },
                "time_limit_min": 30,
                "title": "Midterm drill",
            },
        )

    assert created.status_code == 200, created.text
    body = created.json()
    assert body["question_set"]["kind"] == "test"
    assert body["question_set"]["title"] == "Midterm drill"
    set_id = body["question_set"]["id"]
    questions = body["question_set"]["questions"]
    assert len(questions) == 2

    started = await client.post(
        f"/workspaces/{workspace_id}/study/tests/{set_id}/attempts",
        headers=headers,
    )
    assert started.status_code == 200, started.text
    attempt = started.json()
    assert attempt["time_limit_min"] == 30
    assert len(attempt["questions"]) == 2
    assert "correct_answer" not in attempt["questions"][0]

    mcq_id = questions[0]["id"]
    tf_id = questions[1]["id"]
    submitted = await client.post(
        f"/workspaces/{workspace_id}/study/tests/attempts/{attempt['attempt_id']}/submit",
        headers=headers,
        json={
            "answers": {
                mcq_id: "Preemption",
                tf_id: "False",
            }
        },
    )
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    assert result["score"]["auto_scored_correct"] == 2
    assert result["submitted_at"] is not None

    fetched = await client.get(
        f"/workspaces/{workspace_id}/study/tests/attempts/{attempt['attempt_id']}",
        headers=headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["score"]["auto_scored_correct"] == 2


@pytest.mark.asyncio
async def test_type_counts_validation_rejects_over_10(client):
    email = _unique_email("study-test-validate")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)
    file_id = await _seed_ready_file(workspace_id)

    res = await client.post(
        f"/workspaces/{workspace_id}/study/tests/generate",
        headers=headers,
        json={
            "file_ids": [file_id],
            "type_counts": {
                "mcq": 11,
                "short_answer": 0,
                "calculation": 0,
                "true_false": 0,
            },
        },
    )
    assert res.status_code == 422
