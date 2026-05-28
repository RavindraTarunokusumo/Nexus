# app/evaluation/runner.py
"""Eval runner: orchestrates SUT invocation, judge scoring, and result persistence."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db.models import EvalDataset as EvalDatasetModel
from app.db.models import EvalResult, EvalRun
from app.evaluation.datasets import ClaimExtractionExample, Dataset
from app.evaluation.judges import ClaimExtractionJudge
from app.intelligence.llm_client import (
    _COST_PER_TOKEN_USD,
    ExtractionOutput,
    SentenceBoundedOutput,
)
from app.intelligence.prompts.extract_claims import SYSTEM_PROMPT as SUT_SYSTEM_PROMPT
from app.intelligence.prompts.extract_claims import build_user_prompt as _build_sut_prompt
from app.intelligence.prompts.extract_claims_sentence_bounded import (
    SYSTEM_PROMPT as SB_SYSTEM_PROMPT,
)
from app.intelligence.prompts.extract_claims_sentence_bounded import (
    build_user_prompt as _build_sb_prompt,
)


def _resolve_extractor() -> str:
    """Env override (EXTRACTOR) wins; otherwise fall back to settings.extractor."""
    import os

    env_val = os.environ.get("EXTRACTOR")
    if env_val:
        return env_val
    try:
        from app.config import settings as _settings

        return getattr(_settings, "extractor", "llm")
    except Exception:
        return "llm"


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
            continue
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
        if _resolve_extractor() == "gliner":
            # T1 — local GLiNER2 extraction. No tokens, no API.
            from app.intelligence.gliner_extractor import extract_claims as _gliner_extract

            gliner_out = await asyncio.to_thread(_gliner_extract, document_text)
            pred_claims = [c.model_dump() for c in gliner_out]
            sut_tokens = 0
        elif __import__("os").environ.get("EVAL_SENTENCE_BOUNDED", "0") == "1":
            user_prompt = _build_sb_prompt(document_text, {})
            sb_output, sut_tokens = await llm_client.complete_json(
                model=sut_config.model,
                system=SB_SYSTEM_PROMPT,
                user=user_prompt,
                response_model=SentenceBoundedOutput,
                temperature=sut_config.temperature,
            )
            pred_claims = [c.model_dump() for c in sb_output.to_claims()]
        else:
            user_prompt = _build_sut_prompt(document_text, {})
            sut_output, sut_tokens = await llm_client.complete_json(
                model=sut_config.model,
                system=SUT_SYSTEM_PROMPT,
                user=user_prompt,
                response_model=ExtractionOutput,
                temperature=sut_config.temperature,
            )
            pred_claims = [c.model_dump() for c in sut_output.claims]
        pred_claims = _postfilter_predictions(pred_claims)
        distill_tokens = 0
        if __import__("os").environ.get("EVAL_DISTILL_PASS", "0") == "1" and pred_claims:
            pred_claims, distill_tokens = await _distill_pass(
                document_text=document_text,
                candidates=pred_claims,
                model=sut_config.model,
                llm_client=llm_client,
                temperature=sut_config.temperature,
            )
        sut_tokens += distill_tokens
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
    judge_tokens: int = verdict.pop("total_judge_tokens", 0)
    det_metrics = {k: v for k, v in verdict.items() if k != "per_pair_verdicts"}
    total_tokens = sut_tokens + judge_tokens

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
    return {
        "status": "scored",
        "deterministic_metrics": det_metrics,
        "cost": total_tokens * _COST_PER_TOKEN_USD,
    }


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


_DISTILL_SYSTEM = """\
You are a claim selector. You receive a source text and a list of candidate claims extracted from it.
Return only the canonical, non-overlapping claims — one per distinct fact in the source.
Drop paraphrases, drop framing/interpretation, drop overlapping sub-facts.
Preserve all six fields of any claim you keep. Output the same JSON schema you received.
"""


async def _distill_pass(
    *,
    document_text: str,
    candidates: list[dict],
    model: str,
    llm_client: Any,
    temperature: float,
) -> tuple[list[dict], int]:
    """Second LLM call: filter candidate claims down to canonical, non-overlapping ones."""
    import json as _json

    user = (
        f"Source text:\n{document_text}\n\n"
        f"Candidate claims (JSON):\n{_json.dumps({'claims': candidates}, indent=2)}\n\n"
        "Return only the canonical, non-overlapping claims as JSON matching the same schema."
    )
    distilled, tokens = await llm_client.complete_json(
        model=model,
        system=_DISTILL_SYSTEM,
        user=user,
        response_model=ExtractionOutput,
        temperature=temperature,
    )
    return [c.model_dump() for c in distilled.claims], tokens


def _postfilter_predictions(claims: list[dict]) -> list[dict]:
    """Apply post-extraction filters to SUT predictions.

    Env-controlled:
    - EVAL_CONFIDENCE_THRESHOLD (float, default 0.0): drop claims with confidence < threshold.
    - EVAL_DEDUP (1/0, default 0): drop near-duplicates by token-set Jaccard >= 0.8.
    """
    import os
    import re

    threshold = float(os.environ.get("EVAL_CONFIDENCE_THRESHOLD", "0.0"))
    if threshold > 0:
        claims = [c for c in claims if float(c.get("confidence", 0.0)) >= threshold]

    top_k = int(os.environ.get("EVAL_TOP_K", "0") or "0")
    if top_k > 0:
        # Keep the first-N as emitted; the model tends to put the headline fact first.
        claims = claims[:top_k]

    if os.environ.get("EVAL_ATOMICITY", "0") == "1":
        from app.intelligence.llm_client import is_atomic_claim

        kept_atomic: list[dict] = []
        for c in claims:
            ok, _reason = is_atomic_claim(c.get("claim_text", ""))
            if ok:
                kept_atomic.append(c)
        claims = kept_atomic

    if os.environ.get("EVAL_DEDUP", "0") == "1":
        kept: list[dict] = []

        def _toks(s: str) -> set[str]:
            return set(re.findall(r"[a-z0-9]+", s.lower()))

        for c in claims:
            toks = _toks(c.get("claim_text", ""))
            is_dup = False
            for k in kept:
                k_toks = _toks(k.get("claim_text", ""))
                if not toks or not k_toks:
                    continue
                inter = len(toks & k_toks)
                union = len(toks | k_toks)
                if union and inter / union >= 0.8:
                    is_dup = True
                    break
            if not is_dup:
                kept.append(c)
        claims = kept

    return claims


def _aggregate_scores(score_list: list[dict]) -> dict:
    """Average per-example metric dicts into a run-level aggregate."""
    if not score_list:
        return {}
    keys = ["precision", "recall", "f1", "type_accuracy", "mean_groundedness", "mean_factuality"]
    return {
        k: round(sum(s[k] for s in score_list if k in s) / len(score_list), 4)
        for k in keys
        if any(k in s for s in score_list)
    }
