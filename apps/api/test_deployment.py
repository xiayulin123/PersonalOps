"""Tests for deployment edition helpers."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services import deployment


def test_local_deployment_allows_cursor():
    with patch.object(deployment.settings, "deployment_mode", "local"):
        assert deployment.is_cloud_deployment() is False
        assert "cursor_agent" in deployment.available_chat_modes()
        deployment.assert_chat_mode_allowed("cursor_agent")


def test_cloud_deployment_blocks_cursor():
    with patch.object(deployment.settings, "deployment_mode", "cloud"):
        assert deployment.is_cloud_deployment() is True
        assert deployment.available_chat_modes() == ["langgraph"]
        with pytest.raises(HTTPException) as exc:
            deployment.assert_chat_mode_allowed("cursor_agent")
        assert exc.value.status_code == 400


def test_sync_database_url_postgres():
    from config import Settings

    settings = Settings(
        database_url="postgresql+asyncpg://postgres:secret@db:5432/personalops"
    )
    assert (
        settings.sync_database_url
        == "postgresql+psycopg2://postgres:secret@db:5432/personalops"
    )
