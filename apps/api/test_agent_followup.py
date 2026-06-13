"""Unit tests for Track A follow-up detection and history handling."""

from config import settings
from services.agent.prompts import (
    GENERATOR_SYSTEM_PROMPT,
    _trim_history_content,
    augment_question_with_history,
    build_generator_messages,
    build_history_block,
    is_vague_follow_up,
)

HISTORY = [
    {"role": "user", "content": "What is rl-walker-agent about?"},
    {
        "role": "assistant",
        "content": "It is a TD3 bipedal walker project by Yulin Xia.",
    },
]


def test_who_is_author_is_follow_up():
    assert is_vague_follow_up("Who is the author?", HISTORY)


def test_explain_point_two_is_follow_up():
    assert is_vague_follow_up("Explain point 2 more simply", HISTORY)


def test_new_topic_not_follow_up():
    assert not is_vague_follow_up("What is EDF scheduling algorithm?", HISTORY)


def test_greeting_not_follow_up():
    assert not is_vague_follow_up("hi", HISTORY)


def test_trivial_math_not_follow_up():
    assert not is_vague_follow_up("2+2", HISTORY)


def test_short_continuation_is_follow_up():
    assert is_vague_follow_up("why?", HISTORY)


def test_augment_includes_prior_context():
    aug = augment_question_with_history("Who is the author?", HISTORY)
    assert "Prior user question" in aug
    assert "rl-walker-agent" in aug or "TD3" in aug


def test_augment_skips_new_topic():
    aug = augment_question_with_history(
        "What is EDF scheduling algorithm?", HISTORY
    )
    assert aug == "What is EDF scheduling algorithm?"
    assert "Prior user question" not in aug


def test_default_history_turns_is_five():
    assert settings.agent_history_turns == 5


def test_assistant_trim_keeps_head_and_tail():
    long_answer = "A" * 800 + "CITATION_TAIL" + "Z" * 800
    trimmed = _trim_history_content("assistant", long_answer)
    assert trimmed.startswith("A")
    assert "CITATION_TAIL" in trimmed or trimmed.endswith("Z")
    assert "\n...\n" in trimmed
    assert len(trimmed) <= 1500 + 10


def test_user_trim_is_shorter_than_assistant():
    long_text = "x" * 2000
    assert len(_trim_history_content("user", long_text)) < len(
        _trim_history_content("assistant", long_text)
    )


def test_build_history_block_uses_asymmetric_caps():
    history = [
        {"role": "user", "content": "u" * 1000},
        {"role": "assistant", "content": "a" * 2000},
    ]
    block = build_history_block(history)
    assert "User:" in block
    assert "Assistant:" in block
    assert block.count("u") < 1000
    assert block.count("a") > 600


def test_build_generator_messages_uses_native_roles():
    messages = build_generator_messages(
        "Explain point 2 more simply",
        "study",
        [],
        "File snippet about point 2...",
        [],
        "file_rag",
        HISTORY,
    )
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == GENERATOR_SYSTEM_PROMPT
    assert messages[1]["role"] == "user"
    assert "rl-walker-agent" in messages[1]["content"]
    assert messages[2]["role"] == "assistant"
    assert messages[3]["role"] == "user"
    assert "Explain point 2" in messages[3]["content"]
    assert "Workspace file context" in messages[3]["content"]
    assert "Recent conversation" not in messages[3]["content"]


def test_build_generator_messages_no_flat_history_block_in_context():
    messages = build_generator_messages(
        "Who is the author?",
        "code",
        [],
        "",
        [],
        "file_rag",
        HISTORY,
    )
    assert "Recent conversation (oldest first)" not in messages[-1]["content"]
    assert len(messages) == 4  # system + user + assistant + context user
