"""Unit tests for chat answer prompt rendering (no DB/LLM)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.intelligence.prompts.chat_answer import build_user_prompt

_BASE_BLOCK = {
    "label": "C1",
    "document_title": "Session notes",
    "url": "longmemeval://q1/sess_a",
    "object_type": "personal_fact",
    "score": 0.85,
    "text": "User bought a red car.",
}

_DROPPED_METADATA = ("Title:", "URL:", "Object type:", "Score:", "Epistemic note:", "Capsule:")


def test_build_user_prompt_with_as_of_and_dated_blocks():
    as_of = datetime(2024, 3, 15, 12, 0, tzinfo=timezone.utc)
    published_at = datetime(2023, 4, 10, 23, 7, tzinfo=timezone.utc)
    blocks = [{**_BASE_BLOCK, "published_at": published_at}]

    prompt = build_user_prompt("What car did I buy?", blocks, as_of=as_of)

    assert prompt.startswith("Current date: 2024-03-15 (Fri)")
    assert "Question:\n\nWhat car did I buy?" in prompt
    assert "Date: 2023-04-10 (Mon)" in prompt
    assert "User bought a red car." in prompt
    for dropped in _DROPPED_METADATA:
        assert dropped not in prompt
    assert prompt.index("Current date:") < prompt.index("Question:")
    assert prompt.index("Date:") > prompt.index("Question:")


def test_build_user_prompt_without_as_of_or_published_at():
    blocks = [{**_BASE_BLOCK, "published_at": None}]

    prompt = build_user_prompt("What car did I buy?", blocks)

    assert "Current date:" not in prompt
    assert "Date:" not in prompt
    assert prompt.startswith("Question:\n\nWhat car did I buy?")
    assert "User bought a red car." in prompt
    for dropped in _DROPPED_METADATA:
        assert dropped not in prompt


def test_build_user_prompt_omits_date_line_when_published_at_missing():
    blocks = [dict(_BASE_BLOCK)]

    prompt = build_user_prompt(
        "What car did I buy?", blocks, as_of=datetime(2024, 1, 1, tzinfo=timezone.utc)
    )

    assert "Current date: 2024-01-01 (Mon)" in prompt
    assert "Date:" not in prompt


def test_build_user_prompt_renders_single_evidence_excerpt():
    blocks = [
        {
            **_BASE_BLOCK,
            "evidence": [
                {"text": "first excerpt"},
                {"text": "second excerpt"},
                {"text": "third excerpt"},
            ],
        }
    ]

    prompt = build_user_prompt("What car did I buy?", blocks)

    assert prompt.count("Excerpt:") == 1
    assert "Excerpt: first excerpt" in prompt
    assert "Excerpt: second excerpt" not in prompt
    assert "Excerpt: third excerpt" not in prompt


def test_build_user_prompt_omits_excerpts_when_evidence_missing_or_empty():
    blocks_no_key = [dict(_BASE_BLOCK)]
    blocks_empty = [{**_BASE_BLOCK, "evidence": []}]

    prompt_no_key = build_user_prompt("What car did I buy?", blocks_no_key)
    prompt_empty = build_user_prompt("What car did I buy?", blocks_empty)

    assert "Excerpt:" not in prompt_no_key
    assert "Excerpt:" not in prompt_empty


def test_build_user_prompt_places_excerpt_after_capsule_before_next_block():
    blocks = [
        {
            **_BASE_BLOCK,
            "label": "C1",
            "text": "Capsule one.",
            "evidence": [{"text": "span for C1"}],
        },
        {
            **_BASE_BLOCK,
            "label": "C2",
            "text": "Capsule two.",
            "evidence": [{"text": "span for C2"}],
        },
    ]

    prompt = build_user_prompt("What car did I buy?", blocks)

    c1_section = prompt.split("[C2]")[0]
    assert c1_section.index("Capsule one.") < c1_section.index("Excerpt: span for C1")
    assert "Excerpt: span for C2" in prompt.split("[C2]")[1]


def test_build_user_prompt_renders_role_when_set():
    blocks = [{**_BASE_BLOCK, "role": "primary"}]

    prompt = build_user_prompt("What car did I buy?", blocks)

    assert "Role: primary" in prompt
    for dropped in _DROPPED_METADATA:
        assert dropped not in prompt
