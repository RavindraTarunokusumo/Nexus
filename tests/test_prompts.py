"""Unit tests for extraction prompt builders."""
from app.intelligence.prompts.extract_claims import (
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)


def test_system_prompt_contains_rules():
    assert "atomic" in SYSTEM_PROMPT.lower() or "claim" in SYSTEM_PROMPT.lower()
    assert "json" in SYSTEM_PROMPT.lower()


def test_user_prompt_includes_span_text():
    prompt = build_user_prompt("GPT-5 released.", {"title": "AI News", "source_name": "Feed A"})
    assert "GPT-5 released." in prompt
    assert "AI News" in prompt
    assert "Feed A" in prompt


def test_user_prompt_handles_empty_metadata():
    prompt = build_user_prompt("Some text.", {})
    assert "Some text." in prompt


def test_correction_prompt_includes_error_and_original():
    original = "Extract from: hello world"
    invalid = '{"bad": true}'
    error = "field required: claim_text"
    prompt = build_correction_prompt(original, invalid, error)
    assert original in prompt
    assert invalid in prompt
    assert error in prompt
