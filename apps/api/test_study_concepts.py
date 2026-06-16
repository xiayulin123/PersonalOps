"""S1.1 study concept generation and CRUD tests."""

from __future__ import annotations

import json
import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-study-concepts")
os.environ.setdefault("DEPLOYMENT_MODE", "local")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-study-concepts")
os.environ["RESEND_API_KEY"] = ""

from main import app  # noqa: E402
from models import File, StudyConcept  # noqa: E402


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


async def _seed_ready_file(workspace_id: str, filename: str = "lec01.pdf") -> str:
    from database import SessionLocal

    async with SessionLocal() as db:
        file_record = File(
            workspace_id=workspace_id,
            filename=filename,
            path=f"/tmp/{workspace_id}/{filename}",
            status="ready",
            chunk_count=12,
        )
        db.add(file_record)
        await db.commit()
        await db.refresh(file_record)
        return file_record.id



@pytest.mark.asyncio
async def test_list_concepts_empty(client):
    email = _unique_email("study-concepts-empty")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)

    res = await client.get(f"/workspaces/{workspace_id}/study/concepts", headers=headers)
    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.asyncio
async def test_generate_concepts_persists_sources(client):
    email = _unique_email("study-concepts-gen")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)
    file_id = await _seed_ready_file(workspace_id)

    context_block = "[Source 1: lec01.pdf, page 3]\nMutex protects critical sections."
    sources = [
        {
            "file_id": file_id,
            "filename": "lec01.pdf",
            "page": 3,
            "snippet": "Mutex protects critical sections.",
        }
    ]

    from services.study.schemas import LlmConceptItem, LlmConceptsResponse, LlmSourceRef

    mock_response = LlmConceptsResponse(
        concepts=[
            LlmConceptItem(
                title="Mutex vs Semaphore",
                summary="A mutex allows one owner.",
                key_points=["Mutex = mutual exclusion"],
                example="Printer access",
                source_refs=[LlmSourceRef(filename="lec01.pdf", page=3)],
            )
        ]
    )

    with (
        patch(
            "services.study.generator.retrieve_study_context",
            return_value=(context_block, sources, ["Mutex protects critical sections."], [{}]),
        ),
        patch(
            "services.study.generator._call_concept_llm",
            return_value=mock_response,
        ),
    ):
        res = await client.post(
            f"/workspaces/{workspace_id}/study/concepts/generate",
            headers=headers,
            json={"file_ids": [file_id], "count": 5},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["generated_count"] == 1
    concept = body["concepts"][0]
    assert concept["title"] == "Mutex vs Semaphore"
    assert concept["sources"]
    assert concept["sources"][0]["filename"] == "lec01.pdf"
    assert concept["sources"][0]["file_id"] == file_id


@pytest.mark.asyncio
async def test_patch_concept_mastery(client):
    email = _unique_email("study-concepts-patch")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)

    from database import SessionLocal

    async with SessionLocal() as db:
        record = StudyConcept(
            workspace_id=workspace_id,
            title="Deadlock",
            summary="Four conditions required.",
            key_points_json=json.dumps(["Circular wait"]),
            sources_json=json.dumps(
                [{"file_id": "f1", "filename": "lec07.pdf", "page": 2, "excerpt": "..."}]
            ),
            source_file_ids_json=json.dumps(["f1"]),
            mastery="learning",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        concept_id = record.id

    res = await client.patch(
        f"/workspaces/{workspace_id}/study/concepts/{concept_id}",
        headers=headers,
        json={"title": "Deadlock Conditions", "mastery": "mastered"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["title"] == "Deadlock Conditions"
    assert body["mastery"] == "mastered"


@pytest.mark.asyncio
async def test_delete_concept(client):
    email = _unique_email("study-concepts-del")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = await _create_study_workspace(client, headers)

    from database import SessionLocal

    async with SessionLocal() as db:
        record = StudyConcept(
            workspace_id=workspace_id,
            title="To delete",
            summary="Temporary",
            key_points_json="[]",
            sources_json="[]",
            source_file_ids_json="[]",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        concept_id = record.id

    res = await client.delete(
        f"/workspaces/{workspace_id}/study/concepts/{concept_id}",
        headers=headers,
    )
    assert res.status_code == 204

    listed = await client.get(
        f"/workspaces/{workspace_id}/study/concepts",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json() == []
