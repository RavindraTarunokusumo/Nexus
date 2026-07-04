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


def test_build_user_prompt_with_as_of_and_dated_blocks():
    as_of = datetime(2024, 3, 15, 12, 0, tzinfo=timezone.utc)
    published_at = datetime(2023, 4, 10, 23, 7, tzinfo=timezone.utc)
    blocks = [{**_BASE_BLOCK, "published_at": published_at}]

    prompt = build_user_prompt("What car did I buy?", blocks, as_of=as_of)

    assert prompt.startswith("Current date: 2024-03-15 (Fri)")
    assert "Question:\n\nWhat car did I buy?" in prompt
    assert "URL: longmemeval://q1/sess_a" in prompt
    assert "Date: 2023-04-10 (Mon)" in prompt
    assert prompt.index("Current date:") < prompt.index("Question:")
    assert prompt.index("URL:") < prompt.index("Date:")


def test_build_user_prompt_without_as_of_or_published_at():
    blocks = [{**_BASE_BLOCK, "published_at": None}]

    prompt = build_user_prompt("What car did I buy?", blocks)

    assert "Current date:" not in prompt
    assert "Date:" not in prompt
    assert prompt.startswith("Question:\n\nWhat car did I buy?")
    assert "URL: longmemeval://q1/sess_a" in prompt


def test_build_user_prompt_omits_date_line_when_published_at_missing():
    blocks = [dict(_BASE_BLOCK)]

    prompt = build_user_prompt(
        "What car did I buy?", blocks, as_of=datetime(2024, 1, 1, tzinfo=timezone.utc)
    )

    assert "Current date: 2024-01-01 (Mon)" in prompt
    assert "Date:" not in prompt
