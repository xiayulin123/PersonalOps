"""Unit tests for hybrid web skip and verify failure routing."""

from services.agent.prompts import (
    resolve_verify_failure_action,
    should_skip_web_after_retrieve,
)


def test_skip_web_when_hybrid_local_miss():
    """Indexed files exist but retrieval returned 0 chunks — do not skip web."""
    assert (
        should_skip_web_after_retrieve(
            "What is quantum tunneling?",
            "hybrid",
            retrieved_count=0,
            indexed_files_count=5,
        )
        is False
    )


def test_skip_web_when_hybrid_has_chunks_no_live_info():
    assert (
        should_skip_web_after_retrieve(
            "Summarize my contract",
            "hybrid",
            retrieved_count=8,
            indexed_files_count=3,
        )
        is True
    )


def test_skip_web_when_hybrid_has_chunks_needs_live_info():
    assert (
        should_skip_web_after_retrieve(
            "Latest news about OpenAI today",
            "hybrid",
            retrieved_count=4,
            indexed_files_count=2,
        )
        is False
    )


def test_skip_web_file_only_question():
    assert (
        should_skip_web_after_retrieve(
            "根据文件总结",
            "hybrid",
            retrieved_count=0,
            indexed_files_count=2,
        )
        is True
    )


def test_verify_action_revise_local_when_chunks_exist():
    assert (
        resolve_verify_failure_action(
            retrieved_sources=[{"filename": "a.pdf", "page": 1}],
            web_sources=[],
            tool_settings={"web_search": True},
        )
        == "revise_local"
    )


def test_verify_action_fallback_web_when_local_miss():
    assert (
        resolve_verify_failure_action(
            retrieved_sources=[],
            web_sources=[],
            tool_settings={"web_search": True},
        )
        == "fallback_web"
    )


def test_verify_action_revise_web_when_web_already_fetched():
    assert (
        resolve_verify_failure_action(
            retrieved_sources=[],
            web_sources=[{"title": "t", "url": "https://x", "snippet": "s"}],
            tool_settings={"web_search": True},
        )
        == "revise_web"
    )


def test_verify_action_insufficient_when_no_local_and_web_off():
    assert (
        resolve_verify_failure_action(
            retrieved_sources=[],
            web_sources=[],
            tool_settings={"web_search": False},
        )
        == "insufficient"
    )
