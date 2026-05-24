# tests/evaluation/test_runner.py
"""Unit tests for the eval runner."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.evaluation.datasets import ClaimExtractionExample, Dataset, EvalTask, GoldClaim
from app.evaluation.runner import EvalRunResult, SUTConfig, _aggregate_scores, execute_run


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_dataset(n_examples: int = 2) -> Dataset:
    examples = [
        ClaimExtractionExample(
            example_id=f"ex{i}",
            document_text=f"Document {i} text.",
            gold_claims=[GoldClaim(claim_type="other", claim_text=f"Claim {i}")],
        )
        for i in range(n_examples)
    ]
    return Dataset(
        name="test_ds",
        task=EvalTask.claim_extraction,
        version=1,
        examples=examples,
        checksum="abc123",
    )


def _make_session_factory(dataset_row_id: uuid.UUID | None = None):
    """Return a mock async session factory that behaves like the real one."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    # dataset lookup: return a mock dataset row
    if dataset_row_id is not None:
        mock_ds_row = MagicMock()
        mock_ds_row.id = dataset_row_id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_ds_row
        mock_session.execute = AsyncMock(return_value=mock_result)
    else:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

    # get(EvalRun, run_id) returns a mock run row
    mock_run_row = MagicMock()
    mock_session.get = AsyncMock(return_value=mock_run_row)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    factory = MagicMock()
    factory.return_value = mock_session
    return factory


# ── SUTConfig ─────────────────────────────────────────────────────────────────

class TestSUTConfig:
    def test_defaults(self):
        cfg = SUTConfig(model="my-model", prompt_version="abc")
        assert cfg.temperature == 0.0
        assert cfg.model == "my-model"


# ── _aggregate_scores ─────────────────────────────────────────────────────────

class TestAggregateScores:
    def test_empty_returns_empty(self):
        assert _aggregate_scores([]) == {}

    def test_averages_metrics(self):
        scores = [
            {"precision": 1.0, "recall": 0.5, "f1": 0.67, "type_accuracy": 1.0, "mean_groundedness": 0.8, "mean_factuality": 0.9},
            {"precision": 0.5, "recall": 1.0, "f1": 0.67, "type_accuracy": 0.5, "mean_groundedness": 0.6, "mean_factuality": 0.7},
        ]
        agg = _aggregate_scores(scores)
        assert agg["precision"] == pytest.approx(0.75)
        assert agg["recall"] == pytest.approx(0.75)
        assert "f1" in agg
        assert "type_accuracy" in agg


# ── execute_run ───────────────────────────────────────────────────────────────

class TestExecuteRun:
    @pytest.mark.asyncio
    async def test_raises_if_dataset_not_registered(self):
        sf = _make_session_factory(dataset_row_id=None)  # no dataset row
        mock_client = MagicMock()
        ds = _make_dataset()
        sut_cfg = SUTConfig(model="test-model", prompt_version="abc")

        with pytest.raises(ValueError, match="not registered"):
            await execute_run(
                dataset=ds,
                sut_config=sut_cfg,
                judge_model="judge-model",
                judge_prompt_version="abc",
                session_factory=sf,
                llm_client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_returns_eval_run_result(self):
        ds_id = uuid.uuid4()
        sf = _make_session_factory(dataset_row_id=ds_id)

        # Mock judge to return fixed scores
        mock_judge = AsyncMock()
        mock_judge.score = AsyncMock(return_value={
            "precision": 1.0, "recall": 1.0, "f1": 1.0,
            "type_accuracy": 1.0, "mean_groundedness": 1.0, "mean_factuality": 1.0,
            "per_pair_verdicts": [],
        })

        # Mock SUT (LLMClient) to return ExtractionOutput
        from app.intelligence.llm_client import ExtractionOutput
        mock_client = MagicMock()
        mock_client.complete_json = AsyncMock(return_value=(ExtractionOutput(claims=[]), 50))

        ds = _make_dataset(n_examples=1)
        sut_cfg = SUTConfig(model="sut-model", prompt_version="abc")

        with patch("app.evaluation.runner.ClaimExtractionJudge", return_value=mock_judge):
            result = await execute_run(
                dataset=ds,
                sut_config=sut_cfg,
                judge_model="judge-model",
                judge_prompt_version="abc",
                session_factory=sf,
                llm_client=mock_client,
            )

        assert isinstance(result, EvalRunResult)
        assert result.status in ("completed", "partial")
        assert result.example_count == 1

    @pytest.mark.asyncio
    async def test_budget_gate_stops_execution(self):
        """If max_cost_usd=0, no examples should be scored."""
        ds_id = uuid.uuid4()
        sf = _make_session_factory(dataset_row_id=ds_id)
        mock_client = MagicMock()
        ds = _make_dataset(n_examples=3)
        sut_cfg = SUTConfig(model="sut-model", prompt_version="abc")

        with patch("app.evaluation.runner.ClaimExtractionJudge"):
            result = await execute_run(
                dataset=ds,
                sut_config=sut_cfg,
                judge_model="judge-model",
                judge_prompt_version="abc",
                session_factory=sf,
                llm_client=mock_client,
                max_cost_usd=0.0,  # zero budget → no scoring
            )

        assert result.example_count == 3  # dataset has 3
        assert result.error_count == 0  # none scored, none errored
