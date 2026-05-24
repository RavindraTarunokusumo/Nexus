# tests/evaluation/test_metrics.py
"""Unit tests for deterministic eval metrics."""

from __future__ import annotations

import math

import pytest

from app.evaluation.metrics import (
    align_claims,
    ndcg_at_k,
    precision_at_k,
    precision_recall_f1,
)


class TestPrecisionRecallF1:
    def test_perfect_match(self):
        gold = {"a", "b", "c"}
        pred = {"a", "b", "c"}
        p, r, f = precision_recall_f1(gold, pred)
        assert p == pytest.approx(1.0)
        assert r == pytest.approx(1.0)
        assert f == pytest.approx(1.0)

    def test_no_overlap(self):
        gold = {"a", "b"}
        pred = {"c", "d"}
        p, r, f = precision_recall_f1(gold, pred)
        assert p == pytest.approx(0.0)
        assert r == pytest.approx(0.0)
        assert f == pytest.approx(0.0)

    def test_partial_overlap(self):
        gold = {"a", "b", "c"}
        pred = {"a", "d"}
        p, r, f = precision_recall_f1(gold, pred)
        assert p == pytest.approx(0.5)   # 1/2 pred correct
        assert r == pytest.approx(1/3)   # 1/3 gold found
        # F1 = 2*(0.5*(1/3))/(0.5+(1/3))
        expected_f = 2 * (0.5 * (1/3)) / (0.5 + (1/3))
        assert f == pytest.approx(expected_f)

    def test_empty_gold(self):
        p, r, f = precision_recall_f1(set(), {"a"})
        assert p == pytest.approx(0.0)
        assert r == pytest.approx(0.0)
        assert f == pytest.approx(0.0)

    def test_empty_pred(self):
        p, r, f = precision_recall_f1({"a"}, set())
        assert p == pytest.approx(0.0)
        assert r == pytest.approx(0.0)
        assert f == pytest.approx(0.0)

    def test_both_empty(self):
        p, r, f = precision_recall_f1(set(), set())
        assert p == pytest.approx(1.0)
        assert r == pytest.approx(1.0)
        assert f == pytest.approx(1.0)


class TestPrecisionAtK:
    def test_all_relevant(self):
        gold = {"a", "b", "c"}
        pred = ["a", "b", "c", "d", "e"]
        assert precision_at_k(gold, pred, k=3) == pytest.approx(1.0)

    def test_none_relevant(self):
        gold = {"x"}
        pred = ["a", "b", "c"]
        assert precision_at_k(gold, pred, k=3) == pytest.approx(0.0)

    def test_k_larger_than_pred(self):
        gold = {"a"}
        pred = ["a", "b"]
        assert precision_at_k(gold, pred, k=10) == pytest.approx(1/2)

    def test_k_zero_returns_zero(self):
        gold = {"a"}
        pred = ["a"]
        assert precision_at_k(gold, pred, k=0) == pytest.approx(0.0)


class TestNdcgAtK:
    def test_perfect_ranking(self):
        # relevances = [1, 1, 0] — both relevant items at top
        rel = [1.0, 1.0, 0.0]
        assert ndcg_at_k(rel, k=3) == pytest.approx(1.0)

    def test_reversed_ranking(self):
        # Best item last — nDCG < 1
        rel = [0.0, 0.0, 1.0]
        score = ndcg_at_k(rel, k=3)
        assert 0.0 < score < 1.0

    def test_all_zero(self):
        assert ndcg_at_k([0.0, 0.0], k=2) == pytest.approx(0.0)

    def test_k_truncates(self):
        # Only top-1 matters
        rel = [1.0, 0.0, 0.0]
        assert ndcg_at_k(rel, k=1) == pytest.approx(1.0)


class TestAlignClaims:
    def test_exact_text_match(self):
        gold = [{"claim_text": "OpenAI released GPT-5", "claim_type": "model_release"}]
        pred = [{"claim_text": "OpenAI released GPT-5", "claim_type": "model_release"}]
        pairs = align_claims(gold, pred)
        assert len(pairs) == 1
        assert pairs[0][0] is not None  # gold matched
        assert pairs[0][1] is not None  # pred matched

    def test_unmatched_gold_is_missing(self):
        gold = [{"claim_text": "OpenAI released GPT-5", "claim_type": "model_release"}]
        pred = []
        pairs = align_claims(gold, pred)
        assert len(pairs) == 1
        assert pairs[0][0] is not None   # gold present
        assert pairs[0][1] is None       # no pred match → missing

    def test_unmatched_pred_is_spurious(self):
        gold = []
        pred = [{"claim_text": "Some hallucinated claim", "claim_type": "other"}]
        pairs = align_claims(gold, pred)
        assert len(pairs) == 1
        assert pairs[0][0] is None       # no gold → spurious
        assert pairs[0][1] is not None   # pred present

    def test_empty_both(self):
        pairs = align_claims([], [])
        assert pairs == []

    def test_partial_match(self):
        # Two gold claims, one pred that matches the second
        gold = [
            {"claim_text": "OpenAI released GPT-5", "claim_type": "model_release"},
            {"claim_text": "Google released Gemini", "claim_type": "model_release"},
        ]
        pred = [{"claim_text": "Google released Gemini Ultra", "claim_type": "model_release"}]
        pairs = align_claims(gold, pred, similarity_threshold=0.3)
        # One gold should be unmatched (missing), one pair matched or spurious
        missing = [p for p in pairs if p[0] is not None and p[1] is None]
        assert len(missing) >= 1
