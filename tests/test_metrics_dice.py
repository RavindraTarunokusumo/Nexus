"""Unit tests for app.evaluation.metrics — Sørensen-Dice alignment."""
from __future__ import annotations

from app.evaluation.metrics import _dice, _jaccard, align_claims


def test_dice_identical_strings_is_one() -> None:
    assert _dice("hello world", "hello world") == 1.0


def test_dice_disjoint_strings_is_zero() -> None:
    assert _dice("alpha beta", "gamma delta") == 0.0


def test_dice_substring_above_jaccard() -> None:
    """The motivating case: gold is a substring of pred, Jaccard fails, Dice succeeds."""
    gold = "Anthropic released Claude 4 Opus on March 12, 2025."
    pred = "Anthropic released Claude 4 Opus on March 12, 2025, marking a milestone for the company."
    d = _dice(gold, pred)
    j = _jaccard(gold, pred)
    # Dice >= 2*Jaccard/(1+Jaccard); for J≈0.5, D≈0.67. We just assert ordering.
    assert d > j
    assert d >= 0.5


def test_dice_punctuation_normalization() -> None:
    """'2025.' and '2025,' should both tokenize to '2025'."""
    a = "released on March 12, 2025."
    b = "released on March 12, 2025,"
    assert _dice(a, b) == 1.0


def test_align_claims_matches_substring_pair() -> None:
    gold = [
        {
            "claim_text": "Anthropic released Claude 4 Opus on March 12, 2025.",
            "claim_type": "release.model",
        }
    ]
    pred = [
        {
            "claim_text": (
                "Anthropic released Claude 4 Opus on March 12, 2025, marking "
                "a significant milestone for the company."
            ),
            "claim_type": "release.model",
        }
    ]
    pairs = align_claims(gold, pred)
    assert len(pairs) == 1
    g, p = pairs[0]
    assert g is not None and p is not None
    assert g["claim_text"].startswith("Anthropic")


def test_align_claims_missing_and_spurious() -> None:
    gold = [{"claim_text": "OpenAI released GPT-5.", "claim_type": "release.model"}]
    pred = [{"claim_text": "Anthropic raised $2.5B.", "claim_type": "business.funding"}]
    pairs = align_claims(gold, pred)
    # Dice between disjoint phrases is below 0.5 — no match. Both go to leftovers.
    assert len(pairs) == 2
    shapes = {(g is None, p is None) for g, p in pairs}
    assert (False, True) in shapes   # gold missing
    assert (True, False) in shapes   # pred spurious


def test_align_claims_threshold_respected() -> None:
    # Two pairs, one barely below threshold, one above. Only the higher-Dice
    # pair should be matched.
    gold = [
        {"claim_text": "Anthropic released Claude 4 Opus on March 12.", "claim_type": "x"},
        {"claim_text": "OpenAI shipped a new model.", "claim_type": "x"},
    ]
    pred = [
        {"claim_text": "Anthropic released Claude 4 Opus on March 12.", "claim_type": "x"},
        {"claim_text": "Completely unrelated short clause.", "claim_type": "x"},
    ]
    pairs = align_claims(gold, pred)
    matched = [(g, p) for g, p in pairs if g is not None and p is not None]
    assert len(matched) == 1
    assert "Anthropic" in matched[0][0]["claim_text"]


def test_align_both_empty_returns_empty() -> None:
    assert align_claims([], []) == []


def test_align_only_gold_yields_missing_only() -> None:
    gold = [{"claim_text": "X", "claim_type": "t"}]
    pairs = align_claims(gold, [])
    assert pairs == [(gold[0], None)]


def test_align_only_pred_yields_spurious_only() -> None:
    pred = [{"claim_text": "Y", "claim_type": "t"}]
    pairs = align_claims([], pred)
    assert pairs == [(None, pred[0])]
