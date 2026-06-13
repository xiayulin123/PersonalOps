"""Unit tests for personalization P2 — settings resolution and draft helpers."""

from services.personalization.settings import (
    effective_personalization_prefs,
    personalization_settings_payload,
)


class _WorkspaceStub:
    def __init__(self, raw: str = "{}") -> None:
        self.personalization_settings_json = raw


def test_effective_prefs_use_global_when_no_override(monkeypatch):
    monkeypatch.setattr(
        "services.personalization.settings.settings.personalization_enabled",
        True,
    )
    monkeypatch.setattr(
        "services.personalization.settings.settings.auto_memory_require_approval",
        True,
    )
    prefs = effective_personalization_prefs(_WorkspaceStub())
    assert prefs.auto_learn_enabled is True
    assert prefs.require_approval is True


def test_effective_prefs_workspace_override(monkeypatch):
    monkeypatch.setattr(
        "services.personalization.settings.settings.personalization_enabled",
        True,
    )
    monkeypatch.setattr(
        "services.personalization.settings.settings.auto_memory_require_approval",
        True,
    )
    ws = _WorkspaceStub(
        '{"auto_learn_enabled": false, "require_approval": false}'
    )
    prefs = effective_personalization_prefs(ws)
    assert prefs.auto_learn_enabled is False
    assert prefs.require_approval is False


def test_settings_payload_includes_global_defaults(monkeypatch):
    monkeypatch.setattr(
        "services.personalization.settings.settings.personalization_enabled",
        False,
    )
    monkeypatch.setattr(
        "services.personalization.settings.settings.auto_memory_require_approval",
        True,
    )
    payload = personalization_settings_payload(_WorkspaceStub())
    assert payload["auto_learn_enabled"] is False
    assert payload["global_auto_learn_enabled"] is False
    assert payload["require_approval_override"] is None
