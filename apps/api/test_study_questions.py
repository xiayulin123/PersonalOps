"""S1.2 study practice question tests."""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-study-questions")
os.environ.setdefault("DEPLOYMENT_MODE", "local")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-study-questions")
os.environ["RESEND_API_KEY"] = ""

from main import app  # noqa: E402
from models import File  # noqa: E402


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


@pytest.mark.asyncio
async def test_list_question_sets_empty(client):
    email = _unique_email("study-questions-empty")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)

    res = await client.get(
        f"/workspaces/{workspace_id}/study/question-sets?kind=practice",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.asyncio
async def test_generate_questions_mcq_has_four_options(client):
    email = _unique_email("study-questions-gen")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)
    file_id = await _seed_ready_file(workspace_id)

    context_block = "[Source 1: lec07.pdf, page 3]\nDeadlock requires four conditions."
    sources = [
        {
            "file_id": file_id,
            "filename": "lec07.pdf",
            "page": 3,
            "snippet": "Deadlock requires four conditions.",
        }
    ]

    from services.study.schemas import LlmQuestionItem, LlmQuestionsResponse, LlmSourceRef

    mock_response = LlmQuestionsResponse(
        questions=[
            LlmQuestionItem(
                question_type="mcq",
                prompt="Which is NOT a deadlock condition?",
                options=[
                    "Mutual exclusion",
                    "Preemption",
                    "Hold and wait",
                    "Circular wait",
                ],
                correct_answer="Preemption",
                explanation="Preemption prevents deadlock.",
                topic="Deadlock",
                source_refs=[LlmSourceRef(filename="lec07.pdf", page=3)],
            )
        ]
    )

    with (
        patch(
            "services.study.generator.retrieve_study_context",
            return_value=(context_block, sources, ["Deadlock requires four conditions."], [{}]),
        ),
        patch(
            "services.study.generator._call_questions_llm",
            return_value=mock_response,
        ),
    ):
        res = await client.post(
            f"/workspaces/{workspace_id}/study/questions/generate",
            headers=headers,
            json={
                "file_ids": [file_id],
                "type_counts": {"mcq": 5, "short_answer": 0, "calculation": 0, "true_false": 0},
                "title": "Week 7 practice",
            },
        )

    assert res.status_code == 200, res.text
    body = res.json()
    question_set = body["question_set"]
    assert question_set["title"] == "Week 7 practice"
    assert question_set["question_count"] == 1
    question = question_set["questions"][0]
    assert question["question_type"] == "mcq"
    assert len(question["options"]) == 4
    assert question["sources"]
    assert question["sources"][0]["filename"] == "lec07.pdf"


@pytest.mark.asyncio
async def test_get_question_set_by_id(client):
    email = _unique_email("study-questions-get")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)
    file_id = await _seed_ready_file(workspace_id)

    from services.study.schemas import LlmQuestionItem, LlmQuestionsResponse

    mock_response = LlmQuestionsResponse(
        questions=[
            LlmQuestionItem(
                question_type="short_answer",
                prompt="Define mutex.",
                options=None,
                correct_answer="A lock allowing one owner.",
                explanation="Mutex enforces mutual exclusion.",
                topic="Synchronization",
                source_refs=[],
            )
        ]
    )

    with (
        patch(
            "services.study.generator.retrieve_study_context",
            return_value=("context", [], [], []),
        ),
        patch(
            "services.study.generator._call_questions_llm",
            return_value=mock_response,
        ),
    ):
        created = await client.post(
            f"/workspaces/{workspace_id}/study/questions/generate",
            headers=headers,
            json={"file_ids": [file_id], "type_counts": {"mcq": 0, "short_answer": 1, "calculation": 0, "true_false": 0}},
        )
    assert created.status_code == 200
    set_id = created.json()["question_set"]["id"]

    res = await client.get(
        f"/workspaces/{workspace_id}/study/question-sets/{set_id}",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["questions"][0]["question_type"] == "short_answer"


@pytest.mark.asyncio
async def test_generate_calculation_question_has_solution_steps(client):
    email = _unique_email("study-calc")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)
    file_id = await _seed_ready_file(workspace_id, "hw03.pdf")

    from services.study.schemas import LlmQuestionItem, LlmQuestionsResponse, LlmSourceRef

    mock_response = LlmQuestionsResponse(
        questions=[
            LlmQuestionItem(
                question_type="calculation",
                prompt="Given stress = 200 MPa and safety factor = 2, find allowable stress.",
                options=None,
                correct_answer="100 MPa",
                explanation="Uses allowable = design / safety factor.",
                solution_steps=[
                    "Given: design stress = 200 MPa, SF = 2",
                    "Formula: allowable = design / SF",
                    "Substitute: allowable = 200 / 2 = 100 MPa",
                ],
                topic="Stress",
                source_refs=[LlmSourceRef(filename="hw03.pdf", page=4)],
            )
        ]
    )

    with (
        patch(
            "services.study.generator.retrieve_study_context",
            return_value=("context with formulas", [], [], []),
        ),
        patch(
            "services.study.generator._call_questions_llm",
            return_value=mock_response,
        ),
    ):
        res = await client.post(
            f"/workspaces/{workspace_id}/study/questions/generate",
            headers=headers,
            json={
                "file_ids": [file_id],
                "type_counts": {"mcq": 0, "short_answer": 0, "calculation": 3, "true_false": 0},
                "title": "Calc drill",
            },
        )

    assert res.status_code == 200, res.text
    question = res.json()["question_set"]["questions"][0]
    assert question["question_type"] == "calculation"
    assert len(question["solution_steps"]) >= 2
    assert question["correct_answer"] == "100 MPa"


@pytest.mark.asyncio
async def test_delete_question_set(client):
    email = _unique_email("study-questions-del")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)
    file_id = await _seed_ready_file(workspace_id)

    from services.study.schemas import LlmQuestionItem, LlmQuestionsResponse

    mock_response = LlmQuestionsResponse(
        questions=[
            LlmQuestionItem(
                question_type="true_false",
                prompt="Deadlock is always preventable.",
                options=["True", "False"],
                correct_answer="False",
                explanation="Not always preventable without design.",
                topic="Deadlock",
                source_refs=[],
            )
        ]
    )

    with (
        patch(
            "services.study.generator.retrieve_study_context",
            return_value=("context", [], [], []),
        ),
        patch(
            "services.study.generator._call_questions_llm",
            return_value=mock_response,
        ),
    ):
        created = await client.post(
            f"/workspaces/{workspace_id}/study/questions/generate",
            headers=headers,
            json={"file_ids": [file_id], "type_counts": {"mcq": 0, "short_answer": 0, "calculation": 0, "true_false": 1}},
        )
    set_id = created.json()["question_set"]["id"]

    deleted = await client.delete(
        f"/workspaces/{workspace_id}/study/question-sets/{set_id}",
        headers=headers,
    )
    assert deleted.status_code == 204

    listed = await client.get(
        f"/workspaces/{workspace_id}/study/question-sets?kind=practice",
        headers=headers,
    )
    assert listed.json() == []
