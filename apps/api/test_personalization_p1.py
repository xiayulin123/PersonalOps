"""Unit tests for personalization P1 — distiller parse and memory merge rules."""

from services.agent.prompts import build_memory_block
from services.personalization.distiller_parse import extract_json, normalize_distill_payload


def test_normalize_distill_payload():
    raw = {
        "memories": [{"key": "school", "value": "UofT CS", "confidence": 0.9}],
        "rules": [{"key": "lang", "value": "Chinese + English terms", "confidence": 0.8}],
        "habits": [{"key": "topics", "value": "Often asks about OAuth", "confidence": 0.7}],
        "rejected_patterns": ["API keys"],
    }
    payload = normalize_distill_payload(raw)
    assert len(payload["memories"]) == 1
    assert payload["rules"][0]["kind"] == "rule"
    assert payload["habits"][0]["kind"] == "habit"


def test_build_memory_block_groups_kinds():
    block = build_memory_block(
        [
            {"key": "school", "value": "UofT", "kind": "memory"},
            {"key": "style", "value": "Minimal diff", "kind": "rule"},
            {"key": "topics", "value": "Kubernetes", "kind": "habit"},
        ]
    )
    assert "User facts:" in block
    assert "Rules" in block
    assert "Habits" in block
    assert "Kubernetes" in block


def test_extract_json_from_fence():
    raw = """```json
{"memories": [], "rules": [], "habits": [], "rejected_patterns": []}
```"""
    data = extract_json(raw)
    assert data["memories"] == []
