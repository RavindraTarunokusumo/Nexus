# app/evaluation/runner.py
"""Eval runner: orchestrates SUT invocation, judge scoring, and result persistence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db.models import EvalDataset as EvalDatasetModel
from app.db.models import EvalResult, EvalRun
from app.evaluation.datasets import ClaimExtractionExample, Dataset
from app.evaluation.judges import ClaimExtractionJudge
from app.intelligence.llm_client import ExtractionOutput, _COST_PER_TOKEN_USD

# Import the SUT prompt. Use production prompt if available, fallback otherwise.
try:
    from app.intelligence.prompts.extract_claims import build_user_prompt as _build_sut_prompt
    from app.intelligence.prompts.extract_claims import SYSTEM_PROMPT as SUT_SYSTEM_PROMPT
    _HAS_PRODUCTION_PROMPT = True
except ImportError:
    SUT_SYSTEM_PROMPT = (
        "You are a precise claim extractor. Extract only atomic propositions "
        "directly supported by the provided text. Output valid JSON."
    )
    _HAS_PRODUCTION_PROMPT = False

from app.evaluation.prompts.claim_extraction_judge import JUDGE_SYSTEM_PROMPT as SYSTEM_PROMPT


@dataclass
class SUTConfig:
    """Configuration for the System Under Test (SUT)."""
    model: str
    prompt_version: str
    temperature: float = 0.0


@dataclass
class EvalRunResult:
    """Summary of a completed eval run."""
    run_id: uuid.UUID
    status: str
    aggregate_scores: dict
    total_cost_usd: float
    example_count: int
    error_count: int


async def execute_run(
    *,
    dataset: Dataset,
    sut_config: SUTConfig,
    judge_model: str,
    judge_prompt_version: str,
    session_factory: Any,
    llm_client: Any,
    max_cost_usd: float = 1.0,
    notes: str | None = None,
) -> EvalRunResult:
    """Execute one complete eval run for a claim_extraction dataset.

    Raises ValueError if the dataset has not been registered via
    `nexus eval register-dataset`.
    """
    run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)

    # --- Verify dataset registration ---
    async with session_factory() as session:
        stmt = select(EvalDatasetModel).where(
            EvalDatasetModel.name == dataset.name,
            EvalDatasetModel.task == dataset.task.value,
            EvalDatasetModel.version == dataset.version,
        )
        result = await session.execute(stmt)
        dataset_row = result.scalar_one_or_none()
        if dataset_row is None:
            raise ValueError(
                f"Dataset '{dataset.name}' (task={dataset.task}, v{dataset.version}) "
                "is not registered. Run: nexus eval register-dataset <path>"
            )

        run_row = EvalRun(
            id=run_id,
            dataset_id=dataset_row.id,
            sut_model=sut_config.model,
            sut_prompt_version=sut_config.prompt_version,
            judge_name=ClaimExtractionJudge.name,
            judge_model=judge_model,
            judge_prompt_version=judge_prompt_version,
            started_at=started_at,
            status="running",
            notes=notes,
        )
        session.add(run_row)
        await session.commit()

    judge = ClaimExtractionJudge(model=judge_model, llm_client=llm_client)
    score_accumulator: list[dict] = []
    error_count = 0
    total_cost = 0.0

    for example in dataset.examples:
        if not isinstance(example, ClaimExtractionExample):
            continue  # skip non-claim_extraction examples
        # Budget gate: approximate — current example's cost is checked *before* scoring,
        # so one example may overshoot the limit by its own cost. Gate is not atomic.
        if total_cost >= max_cost_usd:
            break

        example_result = await _score_example(
            run_id=run_id,
            example=example,
            sut_config=sut_config,
            judge=judge,
            session_factory=session_factory,
            llm_client=llm_client,
        )
        if example_result["status"] == "scored":
            score_accumulator.append(example_result["deterministic_metrics"])
            total_cost += example_result.get("cost", 0.0)
        else:
            error_count += 1

    aggregate = _aggregate_scores(score_accumulator)
    completed_at = datetime.now(timezone.utc)
    final_status = "partial" if error_count > 0 else "completed"

    async with session_factory() as session:
        run_row = await session.get(EvalRun, run_id)
        if run_row is not None:
            run_row.completed_at = completed_at
            run_row.status = final_status
            run_row.aggregate_scores = aggregate
            run_row.total_cost_usd = total_cost
            await session.commit()

    return EvalRunResult(
        run_id=run_id,
        status=final_status,
        aggregate_scores=aggregate,
        total_cost_usd=total_cost,
        example_count=len(dataset.examples),
        error_count=error_count,
    )


async def _score_example(
    *,
    run_id: uuid.UUID,
    example: ClaimExtractionExample,
    sut_config: SUTConfig,
    judge: ClaimExtractionJudge,
    session_factory: Any,
    llm_client: Any,
) -> dict:
    """Score one ClaimExtractionExample. Returns {status, deterministic_metrics}."""
    document_text = example.document_text or ""

    try:
        if _HAS_PRODUCTION_PROMPT:
            user_prompt = _build_sut_prompt(document_text, {})
        else:
            user_prompt = f"Extract all factual claims from the following document:\n\n{document_text}"

        sut_output, sut_tokens = await llm_client.complete_json(
            model=sut_config.model,
            system=SUT_SYSTEM_PROMPT,
            user=user_prompt,
            response_model=ExtractionOutput,
            temperature=sut_config.temperature,
        )
        pred_claims = [c.model_dump() for c in sut_output.claims]
    except Exception as exc:  # noqa: BLE001
        await _persist_result(
            run_id=run_id,
            example_id=example.example_id,
            sut_output=None,
            judge_verdict=None,
            deterministic_metrics=None,
            status="error",
            error_message=f"SUT error: {exc}",
            session_factory=session_factory,
        )
        return {"status": "error", "cost": 0.0}

    gold_claims = [c.model_dump() for c in example.gold_claims]
    verdict = await judge.score(
        document_text=document_text,
        gold_claims=gold_claims,
        pred_claims=pred_claims,
    )
    det_metrics = {k: v for k, v in verdict.items() if k != "per_pair_verdicts"}

    await _persist_result(
        run_id=run_id,
        example_id=example.example_id,
        sut_output={"claims": pred_claims},
        judge_verdict=verdict,
        deterministic_metrics=det_metrics,
        status="scored",
        error_message=None,
        session_factory=session_factory,
    )
    return {"status": "scored", "deterministic_metrics": det_metrics, "cost": sut_tokens * _COST_PER_TOKEN_USD}


async def _persist_result(
    *,
    run_id: uuid.UUID,
    example_id: str,
    sut_output: dict | None,
    judge_verdict: dict | None,
    deterministic_metrics: dict | None,
    status: str,
    error_message: str | None,
    session_factory: Any,
) -> None:
    async with session_factory() as session:
        session.add(
            EvalResult(
                id=uuid.uuid4(),
                run_id=run_id,
                example_id=example_id,
                sut_output=sut_output,
                judge_verdict=judge_verdict,
                deterministic_metrics=deterministic_metrics,
                status=status,
                error_message=error_message,
            )
        )
        await session.commit()


def _aggregate_scores(score_list: list[dict]) -> dict:
    """Average per-example metric dicts into a run-level aggregate."""
    if not score_list:
        return {}
    keys = ["precision", "recall", "f1", "type_accuracy", "mean_groundedness", "mean_factuality"]
    return {
        k: round(
            sum(s[k] for s in score_list if k in s) / len(score_list), 4
        )
        for k in keys
        if any(k in s for s in score_list)
    }
