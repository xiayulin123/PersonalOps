from __future__ import annotations

import re

_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_GOOGLE_SECRET = re.compile(r"\bGOCSPX-[A-Za-z0-9_-]+\b")
_GITHUB_TOKEN = re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")
_AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_ENV_ASSIGNMENT = re.compile(
    r"(?im)^([A-Z0-9_]+(?:SECRET|KEY|TOKEN|PASSWORD)[A-Z0-9_]*)=(.+)$"
)
_LONG_B64 = re.compile(r"[A-Za-z0-9+/]{48,}={0,2}")


def redact_secrets(text: str) -> str:
    """Return a copy of text with common secret patterns masked."""
    if not text:
        return ""

    redacted = text
    redacted = _OPENAI_KEY.sub("[REDACTED_OPENAI_KEY]", redacted)
    redacted = _GOOGLE_SECRET.sub("[REDACTED_GOOGLE_SECRET]", redacted)
    redacted = _GITHUB_TOKEN.sub("[REDACTED_GITHUB_TOKEN]", redacted)
    redacted = _AWS_KEY.sub("[REDACTED_AWS_KEY]", redacted)
    redacted = _ENV_ASSIGNMENT.sub(r"\1=[REDACTED]", redacted)
    redacted = _LONG_B64.sub("[REDACTED_BLOB]", redacted)
    return redacted
