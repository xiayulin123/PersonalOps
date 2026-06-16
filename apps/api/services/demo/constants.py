"""Fixed IDs for the PersonalOps demo account."""

from __future__ import annotations

from config import settings

DEMO_USER_ID = settings.demo_user_id

WS_STUDY = "00000000-0000-4000-8000-000000010001"
WS_CODE = "00000000-0000-4000-8000-000000010002"
WS_LIFE = "00000000-0000-4000-8000-000000010003"
WS_CAREER = "00000000-0000-4000-8000-000000010004"

DEMO_WORKSPACES: tuple[tuple[str, str, str], ...] = (
    (WS_STUDY, "CE457A", "study"),
    (WS_CODE, "PersonalOps Dev", "code"),
    (WS_LIFE, "my life", "life"),
    (WS_CAREER, "career Test", "career"),
)

DEMO_GCS_BUNDLE_PREFIX = "system/demo-bundle"
