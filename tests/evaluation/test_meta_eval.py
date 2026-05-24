# tests/evaluation/test_meta_eval.py
"""Unit tests for judge calibration (Cohen's κ, Pearson r)."""
import pytest

from app.evaluation.meta_eval import compute_kappa, compute_pearson


class TestCohenKappa:
    def test_perfect_agreement(self):
        labels = ["exact", "partial", "missing"]
        assert compute_kappa(labels, labels) == pytest.approx(1.0)

    def test_zero_agreement_beyond_chance(self):
        # When judge and human use overlapping categories but never agree
        # j: 5 "exact", 5 "missing"; h: 5 "missing", 5 "exact" → po=0, pe>0 → κ<0
        j = ["exact"] * 5 + ["missing"] * 5
        h = ["missing"] * 5 + ["exact"] * 5
        k = compute_kappa(j, h)
        assert k < 0.0  # below chance

    def test_substantial_agreement(self):
        # 8/10 match — should be well above 0.6
        j = ["exact"] * 8 + ["partial", "missing"]
        h = ["exact"] * 8 + ["partial", "missing"]
        assert compute_kappa(j, h) == pytest.approx(1.0)

    def test_fully_disjoint_categories_returns_zero(self):
        # When raters use entirely different category sets, marginals never overlap:
        # pe = sum(p_j(c)*p_h(c)) = 0 because for each c, one rater's proportion is 0.
        # po = 0 (no matches), so κ = (0 - 0) / (1 - 0) = 0.0, NOT negative.
        j = ["exact"] * 10
        h = ["missing"] * 10
        assert compute_kappa(j, h) == pytest.approx(0.0)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            compute_kappa(["exact"], ["exact", "partial"])


class TestPearson:
    def test_perfect_positive_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0]
        y = [2.0, 4.0, 6.0, 8.0]
        assert compute_pearson(x, y) == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        x = [1.0, 2.0, 3.0]
        y = [3.0, 2.0, 1.0]
        assert compute_pearson(x, y) == pytest.approx(-1.0)

    def test_no_correlation(self):
        # Constant y → zero denominator → returns 0.0
        x = [1.0, 2.0, 3.0]
        y = [5.0, 5.0, 5.0]
        assert compute_pearson(x, y) == pytest.approx(0.0)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            compute_pearson([1.0], [1.0, 2.0])
