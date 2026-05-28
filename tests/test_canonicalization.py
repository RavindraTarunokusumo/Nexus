"""Unit tests for app.intelligence.canonicalization — signature builder + entity aliases."""

from __future__ import annotations

import pytest

from app.intelligence.canonicalization import (
    claim_signature,
    extract_date_anchor,
    normalize_entity,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Anthropic", "Anthropic"),
        ("anthropic", "Anthropic"),
        ("anthropic pbc", "Anthropic"),
        ("OpenAI", "OpenAI"),
        ("open ai", "OpenAI"),
        ("OPEN AI", "OpenAI"),
        ("DeepMind", "Google DeepMind"),
        ("Google DeepMind", "Google DeepMind"),
        ("Hugging Face", "Hugging Face"),
        ("huggingface", "Hugging Face"),
    ],
)
def test_normalize_entity_alias_resolution(raw: str, expected: str) -> None:
    assert normalize_entity(raw) == expected


def test_normalize_entity_passthrough_for_unknown() -> None:
    # No alias hit → returns the input stripped, original case preserved.
    assert normalize_entity("Some Novel Corp") == "Some Novel Corp"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Released on March 12, 2025.", "2025-03-12"),
        ("Released in March 2025.", "2025-03"),
        ("Released in 2025.", "2025"),
        ("No date at all here.", None),
        ("Some 1999 reference (older).", None),  # 1999 < 2000 cutoff in regex
    ],
)
def test_extract_date_anchor(text: str, expected: str | None) -> None:
    assert extract_date_anchor(text) == expected


def test_claim_signature_groups_alias_variants() -> None:
    sig_a = claim_signature(
        "release.model",
        ["Anthropic", "Claude 4 Opus"],
        "Anthropic released Claude 4 Opus on March 12, 2025.",
    )
    sig_b = claim_signature(
        "release.model",
        ["anthropic", "Claude 4 Opus"],  # case-variant
        "On March 12, 2025, anthropic launched Claude 4 Opus.",
    )
    assert sig_a == sig_b


def test_claim_signature_distinguishes_types() -> None:
    sig_release = claim_signature("release.model", ["OpenAI", "GPT-5"], "OpenAI released GPT-5.")
    sig_funding = claim_signature("business.funding", ["OpenAI"], "OpenAI raised $40B.")
    assert sig_release != sig_funding


def test_claim_signature_distinguishes_date_granularity() -> None:
    # 'March 12, 2025' vs 'March 2025' must be treated as different anchors —
    # conservative behavior to avoid false-merging coarse and fine dates.
    sig_day = claim_signature(
        "release.model", ["Anthropic"], "Anthropic shipped X on March 12, 2025."
    )
    sig_month = claim_signature(
        "release.model", ["Anthropic"], "Anthropic shipped X in March 2025."
    )
    assert sig_day != sig_month
