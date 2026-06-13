"""Unit tests for personalization P0 — secret redaction and period helpers."""

from datetime import date

from services.personalization.prompt_log import week_start
from services.personalization.redact import redact_secrets


def test_redact_openai_key():
    raw = "Use key sk-abcdefghijklmnopqrstuvwxyz123456 for testing"
    redacted = redact_secrets(raw)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in redacted
    assert "[REDACTED_OPENAI_KEY]" in redacted


def test_redact_google_secret():
    raw = "GOOGLE_CLIENT_SECRET=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"
    redacted = redact_secrets(raw)
    assert "GOCSPX-" not in redacted
    assert "[REDACTED]" in redacted or "[REDACTED_GOOGLE_SECRET]" in redacted


def test_redact_leaves_normal_text():
    raw = "Explain EDF scheduling in Chinese with English terms."
    assert redact_secrets(raw) == raw


def test_week_start_is_monday():
    # 2026-06-11 is a Thursday
    assert week_start(date(2026, 6, 11)) == date(2026, 6, 8)
