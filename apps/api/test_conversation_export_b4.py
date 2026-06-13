"""B4 GCS conversation export tests."""

from __future__ import annotations

import json
import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-b4-tests-only")
os.environ.setdefault("DEPLOYMENT_MODE", "cloud")


def test_conversation_object_path():
    from services.storage.gcs_app_storage import conversation_object_path

    path = conversation_object_path("user-1", "ws-1", "conv-1")
    assert path == "users/user-1/workspaces/ws-1/conversations/conv-1.jsonl"


def test_serialize_conversation_payload():
    from datetime import datetime

    from models import Conversation, Message
    from services.storage.conversation_export import _serialize_conversation

    conversation = Conversation(
        id="conv-1",
        workspace_id="ws-1",
        title="Test chat",
    )
    messages = [
        Message(
            id="m1",
            conversation_id="conv-1",
            role="user",
            content="hello",
            created_at=datetime(2026, 6, 13, 12, 0, 0),
        ),
        Message(
            id="m2",
            conversation_id="conv-1",
            role="assistant",
            content="hi",
            sources_json='{"route":"rag"}',
            created_at=datetime(2026, 6, 13, 12, 0, 1),
        ),
    ]

    payload = _serialize_conversation(conversation, messages).decode("utf-8")
    lines = [json.loads(line) for line in payload.splitlines() if line.strip()]
    assert lines[0]["type"] == "meta"
    assert lines[0]["message_count"] == 2
    assert lines[1]["role"] == "user"
    assert lines[2]["metadata"]["route"] == "rag"


@pytest.mark.asyncio
async def test_export_conversation_to_gcs_updates_db():
    from datetime import datetime

    from database import SessionLocal
    from models import Conversation, Message, User, Workspace
    from services.storage.conversation_export import export_conversation_to_gcs

    async with SessionLocal() as db:
        user = User(email=f"b4-export-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        db.add(user)
        await db.flush()
        workspace = Workspace(name="B4 WS", type="study", user_id=user.id)
        db.add(workspace)
        await db.flush()
        conversation = Conversation(workspace_id=workspace.id, title="Chat")
        db.add(conversation)
        await db.flush()
        db.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content="question",
                created_at=datetime(2026, 6, 13, 12, 0, 0),
            )
        )
        await db.commit()
        user_id = user.id
        workspace_id = workspace.id
        conversation_id = conversation.id

    fake_uri = f"gs://personalops-personal/users/{user_id}/workspaces/{workspace_id}/conversations/{conversation_id}.jsonl"
    with patch(
        "services.storage.conversation_export.gcs.export_conversation_jsonl",
        return_value=fake_uri,
    ):
        with patch(
            "services.storage.conversation_export.should_export_conversations",
            return_value=True,
        ):
            uri = await export_conversation_to_gcs(
                user_id=user_id,
                workspace_id=workspace_id,
                conversation_id=conversation_id,
            )

    assert uri == fake_uri

    async with SessionLocal() as db:
        row = await db.get(Conversation, conversation_id)
        assert row is not None
        assert row.gcs_export_uri == fake_uri
        assert row.gcs_exported_at is not None


def test_parse_conversation_export_payload_roundtrip():
    from datetime import datetime

    from models import Conversation, Message
    from services.storage.conversation_export import (
        _serialize_conversation,
        parse_conversation_export_payload,
    )

    conversation = Conversation(
        id="conv-2",
        workspace_id="ws-2",
        title="Roundtrip",
    )
    messages = [
        Message(
            id="m1",
            conversation_id="conv-2",
            role="user",
            content="hello",
            created_at=datetime(2026, 6, 13, 12, 0, 0),
        )
    ]
    payload = _serialize_conversation(conversation, messages)
    meta, restored_messages = parse_conversation_export_payload(payload)
    assert meta["conversation_id"] == "conv-2"
    assert len(restored_messages) == 1
    assert restored_messages[0]["content"] == "hello"


@pytest.mark.asyncio
async def test_restore_conversation_from_gcs_export_creates_db_rows():
    from datetime import datetime

    from database import SessionLocal
    from models import Conversation, Message, User, Workspace
    from services.storage.conversation_export import (
        _serialize_conversation,
        restore_conversation_from_gcs_export,
    )

    async with SessionLocal() as db:
        user = User(email=f"b4-restore-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        db.add(user)
        await db.flush()
        workspace = Workspace(name="Restore WS", type="study", user_id=user.id)
        db.add(workspace)
        await db.commit()
        user_id = user.id
        workspace_id = workspace.id

    conversation_id = f"conv-restore-{uuid.uuid4().hex[:8]}"
    conversation = Conversation(
        id=conversation_id,
        workspace_id=workspace_id,
        title="Restored chat",
    )
    messages = [
        Message(
            id=f"m-restore-{uuid.uuid4().hex[:8]}",
            conversation_id=conversation.id,
            role="user",
            content="saved question",
            created_at=datetime(2026, 6, 13, 12, 0, 0),
        ),
        Message(
            id=f"m-restore-{uuid.uuid4().hex[:8]}",
            conversation_id=conversation.id,
            role="assistant",
            content="saved answer",
            sources_json='{"route":"rag"}',
            created_at=datetime(2026, 6, 13, 12, 0, 1),
        ),
    ]
    payload = _serialize_conversation(conversation, messages)
    gcs_uri = (
        f"gs://personalops-personal/users/{user_id}/workspaces/"
        f"{workspace_id}/conversations/{conversation_id}.jsonl"
    )

    with patch(
        "services.storage.conversation_export.gcs.download_blob_bytes",
        return_value=payload,
    ):
        with patch(
            "services.storage.conversation_export.gcs.is_gcs_app_storage_enabled",
            return_value=True,
        ):
            status = await restore_conversation_from_gcs_export(
                user_id=user_id,
                gcs_uri=gcs_uri,
            )

    assert status == "restored"

    async with SessionLocal() as db:
        row = await db.get(Conversation, conversation_id)
        assert row is not None
        assert row.title == "Restored chat"
        result = await db.execute(
            select(Message).where(Message.conversation_id == conversation_id)
        )
        restored = list(result.scalars().all())
        assert len(restored) == 2
        assert restored[0].content == "saved question"
        assert restored[1].sources_json is not None
        assert json.loads(restored[1].sources_json)["route"] == "rag"


@pytest.mark.asyncio
async def test_restore_skips_when_messages_already_exist():
    from datetime import datetime

    from database import SessionLocal
    from models import Conversation, Message, User, Workspace
    from services.storage.conversation_export import (
        _serialize_conversation,
        restore_conversation_from_gcs_export,
    )

    async with SessionLocal() as db:
        user = User(email=f"b4-skip-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        db.add(user)
        await db.flush()
        workspace = Workspace(name="Skip WS", type="study", user_id=user.id)
        db.add(workspace)
        await db.flush()
        conversation = Conversation(workspace_id=workspace.id, title="Existing")
        db.add(conversation)
        await db.flush()
        db.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content="already here",
                created_at=datetime(2026, 6, 13, 12, 0, 0),
            )
        )
        await db.commit()
        user_id = user.id
        workspace_id = workspace.id
        conversation_id = conversation.id

    payload = _serialize_conversation(conversation, [])
    gcs_uri = (
        f"gs://personalops-personal/users/{user_id}/workspaces/"
        f"{workspace_id}/conversations/{conversation_id}.jsonl"
    )

    with patch(
        "services.storage.conversation_export.gcs.download_blob_bytes",
        return_value=payload,
    ):
        status = await restore_conversation_from_gcs_export(
            user_id=user_id,
            gcs_uri=gcs_uri,
        )

    assert status == "skipped"
