# tests/evaluation/test_judges.py
"""Unit tests for LLM judge classes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.evaluation.judges import (
    BriefSynthesisJudge,
    ClaimExtractionJudge,
    GroundedAnswerJudge,
)


class TestClaimExtractionJudge:
    def _make_judge(self, mock_verdicts: list[dict]) -> ClaimExtractionJudge:
        """Build a ClaimExtractionJudge with a mocked LLMClient."""
        mock_client = MagicMock()
        # complete_json returns (ClaimPairVerdict, total_tokens)
        from app.evaluation.prompts.claim_extraction_judge import ClaimPairVerdict
        verdicts = [
            ClaimPairVerdict(**v) for v in mock_verdicts
        ]
        mock_client.complete_json = AsyncMock(side_effect=[
            (v, 100) for v in verdicts
        ])
        return ClaimExtractionJudge(model="test-model", llm_client=mock_client)

    @pytest.mark.asyncio
    async def test_name_is_class_attribute(self):
        assert ClaimExtractionJudge.name == "claim_extraction_judge_v1"

    @pytest.mark.asyncio
    async def test_perfect_match_score(self):
        """One gold, one pred, exact match — should return high scores."""
        judge = self._make_judge([
            {
                "match_status": "exact",
                "type_correct": True,
                "groundedness": 1.0,
                "factuality": 1.0,
                "rationale": "Perfect match.",
            }
        ])
        result = await judge.score(
            document_text="Anthropic released Claude 4.",
            gold_claims=[{"claim_text": "Anthropic released Claude 4", "claim_type": "model_release"}],
            pred_claims=[{"claim_text": "Anthropic released Claude 4", "claim_type": "model_release"}],
        )
        assert result["precision"] == pytest.approx(1.0)
        assert result["recall"] == pytest.approx(1.0)
        assert result["f1"] == pytest.approx(1.0)
        assert result["type_accuracy"] == pytest.approx(1.0)
        assert result["mean_groundedness"] == pytest.approx(1.0)
        assert result["mean_factuality"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_missing_claim_lowers_recall(self):
        """One gold, no pred — recall should be 0."""
        judge = self._make_judge([])  # no LLM calls for missing claims
        result = await judge.score(
            document_text="Anthropic released Claude 4.",
            gold_claims=[{"claim_text": "Anthropic released Claude 4", "claim_type": "model_release"}],
            pred_claims=[],
        )
        assert result["recall"] == pytest.approx(0.0)
        assert result["precision"] == pytest.approx(0.0)  # no predictions

    @pytest.mark.asyncio
    async def test_spurious_claim_lowers_precision(self):
        """No gold, one pred — precision should be 0."""
        judge = self._make_judge([])  # no LLM calls for spurious with no gold
        result = await judge.score(
            document_text="Some document.",
            gold_claims=[],
            pred_claims=[{"claim_text": "Made up claim", "claim_type": "other"}],
        )
        assert result["precision"] == pytest.approx(0.0)
        assert result["recall"] == pytest.approx(0.0)  # no gold

    @pytest.mark.asyncio
    async def test_returns_per_pair_verdicts(self):
        """score() result must include per_pair_verdicts list."""
        judge = self._make_judge([
            {
                "match_status": "exact",
                "type_correct": True,
                "groundedness": 0.9,
                "factuality": 0.9,
                "rationale": "Good.",
            }
        ])
        result = await judge.score(
            document_text="doc",
            gold_claims=[{"claim_text": "x", "claim_type": "other"}],
            pred_claims=[{"claim_text": "x", "claim_type": "other"}],
        )
        assert "per_pair_verdicts" in result
        assert len(result["per_pair_verdicts"]) >= 1


class TestStubJudges:
    @pytest.mark.asyncio
    async def test_brief_synthesis_judge_raises(self):
        j = BriefSynthesisJudge()
        with pytest.raises(NotImplementedError, match="Phase 4"):
            await j.score("doc", {}, {})

    @pytest.mark.asyncio
    async def test_grounded_answer_judge_raises(self):
        j = GroundedAnswerJudge()
        with pytest.raises(NotImplementedError, match="Phase 4"):
            await j.score("doc", "query", {})
