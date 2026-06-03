# tests/evaluation/test_judges.py
"""Unit tests for LLM judge classes (v0.7 semantic-object judge)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.evaluation.judges import (
    BriefSynthesisJudge,
    GroundedAnswerJudge,
    SemanticObjectJudge,
)
from app.evaluation.prompts.semantic_object_judge import SemanticObjectPairVerdict


def _make_judge(mock_verdicts: list[dict]) -> SemanticObjectJudge:
    """Build a SemanticObjectJudge with a mocked LLMClient."""
    mock_client = MagicMock()
    verdicts = [SemanticObjectPairVerdict(**v) for v in mock_verdicts]
    mock_client.complete_json = AsyncMock(side_effect=[(v, 100) for v in verdicts])
    return SemanticObjectJudge(model="test-model", llm_client=mock_client)


def _obj(text: str, **overrides) -> dict:
    base = {
        "text": text,
        "core_type": "event",
        "domain_family": "model_system",
        "domain_object_type": "model_release",
        "function": "f",
        "facets": {"orgs": ["X"]},
        "epistemic": {
            "status": "asserted_by_source",
            "source_authority": "primary",
            "confidence": 0.9,
            "evidence_quality": "high",
        },
        "salience": 0.8,
        "mvp_claim_type": "model_release",
    }
    base.update(overrides)
    return base


class TestSemanticObjectJudge:
    def test_name_is_class_attribute(self):
        assert SemanticObjectJudge.name == "semantic_object_judge_v1"

    @pytest.mark.asyncio
    async def test_perfect_match_score(self):
        judge = _make_judge(
            [
                {
                    "match_status": "exact",
                    "mvp_claim_type_correct": True,
                    "core_type_correct": True,
                    "domain_family_correct": True,
                    "groundedness": 1.0,
                    "factuality": 1.0,
                    "capsule_completeness": 0.9,
                    "rationale": "Perfect match.",
                }
            ]
        )
        result = await judge.score(
            document_text="Anthropic released Claude 4.",
            gold_objects=[_obj("Anthropic released Claude 4")],
            pred_objects=[_obj("Anthropic released Claude 4")],
        )
        assert result["precision"] == pytest.approx(1.0)
        assert result["recall"] == pytest.approx(1.0)
        assert result["f1"] == pytest.approx(1.0)
        assert result["mvp_claim_type_projection_accuracy"] == pytest.approx(1.0)
        assert result["core_type_accuracy"] == pytest.approx(1.0)
        assert result["domain_family_accuracy"] == pytest.approx(1.0)
        assert result["mean_groundedness"] == pytest.approx(1.0)
        assert result["mean_factuality"] == pytest.approx(1.0)
        assert result["mean_capsule_completeness"] == pytest.approx(0.9)
        assert result["salience_precision"] == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_missing_object_lowers_recall(self):
        judge = _make_judge([])  # no LLM call needed when pred is empty (gold,None unmatched)
        # Actually align_semantic_objects produces (gold, None) pair which triggers an
        # LLM call for the missing-side judgement. Provide one verdict.
        judge = _make_judge(
            [
                {
                    "match_status": "missing",
                    "mvp_claim_type_correct": False,
                    "core_type_correct": False,
                    "domain_family_correct": False,
                    "groundedness": 0.0,
                    "factuality": 0.0,
                    "capsule_completeness": 0.0,
                    "rationale": "Missing.",
                }
            ]
        )
        result = await judge.score(
            document_text="doc",
            gold_objects=[_obj("Anthropic released Claude 4")],
            pred_objects=[],
        )
        assert result["recall"] == pytest.approx(0.0)
        assert result["precision"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_spurious_object_lowers_precision(self):
        judge = _make_judge(
            [
                {
                    "match_status": "spurious",
                    "mvp_claim_type_correct": False,
                    "core_type_correct": False,
                    "domain_family_correct": False,
                    "groundedness": 0.0,
                    "factuality": 0.0,
                    "capsule_completeness": 0.0,
                    "rationale": "Hallucinated.",
                }
            ]
        )
        result = await judge.score(
            document_text="doc",
            gold_objects=[],
            pred_objects=[_obj("Made-up claim")],
        )
        assert result["precision"] == pytest.approx(0.0)
        assert result["recall"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_returns_per_pair_verdicts(self):
        judge = _make_judge(
            [
                {
                    "match_status": "exact",
                    "mvp_claim_type_correct": True,
                    "core_type_correct": True,
                    "domain_family_correct": True,
                    "groundedness": 0.9,
                    "factuality": 0.9,
                    "capsule_completeness": 0.8,
                    "rationale": "Good.",
                }
            ]
        )
        result = await judge.score(
            document_text="doc",
            gold_objects=[_obj("x")],
            pred_objects=[_obj("x")],
        )
        assert "per_pair_verdicts" in result
        assert len(result["per_pair_verdicts"]) >= 1

    @pytest.mark.asyncio
    async def test_both_empty_returns_perfect(self):
        judge = _make_judge([])
        result = await judge.score(document_text="doc", gold_objects=[], pred_objects=[])
        assert result["precision"] == pytest.approx(1.0)
        assert result["recall"] == pytest.approx(1.0)
        assert result["f1"] == pytest.approx(1.0)


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
