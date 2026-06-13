from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Workspace
from services.personalization.archive import archive_is_configured


DEFAULT_PERSONALIZATION_SETTINGS_JSON = "{}"


@dataclass(frozen=True)
class PersonalizationPrefs:
    auto_learn_enabled: bool
    require_approval: bool


def _parse_overrides(raw: str | None) -> dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def effective_personalization_prefs(workspace: Workspace) -> PersonalizationPrefs:
    overrides = _parse_overrides(workspace.personalization_settings_json)
    enabled = overrides.get("auto_learn_enabled")
    if enabled is None:
        enabled = settings.personalization_enabled
    require = overrides.get("require_approval")
    if require is None:
        require = settings.auto_memory_require_approval
    return PersonalizationPrefs(bool(enabled), bool(require))


def personalization_settings_payload(workspace: Workspace) -> dict[str, Any]:
    overrides = _parse_overrides(workspace.personalization_settings_json)
    prefs = effective_personalization_prefs(workspace)
    return {
        "auto_learn_enabled": prefs.auto_learn_enabled,
        "require_approval": prefs.require_approval,
        "auto_learn_override": overrides.get("auto_learn_enabled"),
        "require_approval_override": overrides.get("require_approval"),
        "global_auto_learn_enabled": settings.personalization_enabled,
        "global_require_approval": settings.auto_memory_require_approval,
        "cloud_archive_enabled": settings.cloud_archive_enabled,
        "cloud_archive_provider": settings.cloud_archive_provider,
        "cloud_archive_configured": archive_is_configured(),
    }


async def update_personalization_settings(
    db: AsyncSession,
    workspace: Workspace,
    *,
    auto_learn_enabled: bool | None = None,
    require_approval: bool | None = None,
) -> dict[str, Any]:
    overrides = _parse_overrides(workspace.personalization_settings_json)
    if auto_learn_enabled is not None:
        overrides["auto_learn_enabled"] = auto_learn_enabled
    if require_approval is not None:
        overrides["require_approval"] = require_approval
    workspace.personalization_settings_json = json.dumps(overrides)
    await db.flush()
    return personalization_settings_payload(workspace)
