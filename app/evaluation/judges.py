# app/evaluation/judges.py
"""LLM-as-a-Judge evaluators for each pipeline output type."""

from __future__ import annotations

import asyncio
from typing import Any

from app.evaluation.metrics import align_claims
from app.evaluation.prompts.claim_extraction_judge import (
    JUDGE_SYSTEM_PROMPT,
    ClaimPairVerdict,
    build_judge_prompt,
)


class ClaimExtractionJudge:
    """LLM judge for claim extraction quality.

    Aligns predicted claims to gold claims by Jaccard similarity, then
    calls the LLM to score each (gold, pred) pair.
    """

    name: str = "claim_extraction_judge_v1"

    def __init__(self, model: str, llm_client: Any) -> None:
        self._model = model
        self._llm_client = llm_client

    async def score(
        self,
        document_text: str,
        gold_claims: list[dict],
        pred_claims: list[dict],
    ) -> dict:
        """Score predicted claims against gold claims.

        Returns a dict with:
            precision, recall, f1         — set-level P/R/F1 (matched = "exact" or "partial")
            type_accuracy                  — fraction of matched pairs with correct claim_type
            mean_groundedness              — average groundedness over matched pairs
            mean_factuality                — average factuality over matched pairs
            per_pair_verdicts              — list of per-pair verdict dicts
        """
        pairs = align_claims(gold_claims, pred_claims)

        # Judge all pairs concurrently — each call is independent.
        judgments = await asyncio.gather(
            *[self._judge_pair(document_text, gold, pred) for gold, pred in pairs]
        )

        n_matched = 0
        per_pair: list[dict] = []
        type_correct_flags: list[bool] = []
        groundedness_scores: list[float] = []
        factuality_scores: list[float] = []
        total_judge_tokens: int = 0

        for verdict, tokens in judgments:
            total_judge_tokens += tokens
            per_pair.append(verdict)
            if verdict["match_status"] in ("exact", "partial"):
                n_matched += 1
                type_correct_flags.append(bool(verdict["type_correct"]))
                groundedness_scores.append(verdict["groundedness"])
                factuality_scores.append(verdict["factuality"])

        n_gold = len(gold_claims)
        n_pred = len(pred_claims)

        precision = n_matched / n_pred if n_pred > 0 else 0.0
        recall = n_matched / n_gold if n_gold > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        if n_gold == 0 and n_pred == 0:
            precision = recall = f1 = 1.0

        type_accuracy = (
            sum(type_correct_flags) / len(type_correct_flags) if type_correct_flags else 0.0
        )
        mean_groundedness = (
            sum(groundedness_scores) / len(groundedness_scores) if groundedness_scores else 0.0
        )
        mean_factuality = (
            sum(factuality_scores) / len(factuality_scores) if factuality_scores else 0.0
        )

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "type_accuracy": round(type_accuracy, 4),
            "mean_groundedness": round(mean_groundedness, 4),
            "mean_factuality": round(mean_factuality, 4),
            "per_pair_verdicts": per_pair,
            "total_judge_tokens": total_judge_tokens,
        }

    async def _judge_pair(
        self,
        document_text: str,
        gold: dict | None,
        pred: dict | None,
    ) -> tuple[dict, int]:
        """Call LLM judge for a single (gold, pred) pair.

        Returns (verdict_dict, tokens_used). Tokens are 0 on error or when LLM is skipped.
        """
        # For pure missing/spurious with no counterpart, skip LLM call
        if gold is None and pred is None:
            return {
                "match_status": "error",
                "type_correct": False,
                "groundedness": 0.0,
                "factuality": 0.0,
                "rationale": "Both gold and pred are None — alignment error.",
            }, 0

        user_prompt = build_judge_prompt(document_text, gold, pred)
        try:
            verdict, tokens = await self._llm_client.complete_json(
                model=self._model,
                system=JUDGE_SYSTEM_PROMPT,
                user=user_prompt,
                response_model=ClaimPairVerdict,
                temperature=0.0,
            )
            return verdict.model_dump(), tokens
        except Exception as exc:  # noqa: BLE001
            return {
                "match_status": "error",
                "type_correct": False,
                "groundedness": 0.0,
                "factuality": 0.0,
                "rationale": f"Judge LLM call failed: {exc}",
            }, 0


class BriefSynthesisJudge:
    """Stub — Phase 4 (brief synthesis) not yet implemented."""

    async def score(self, document_text: str, gold: dict, pred: dict) -> dict:
        raise NotImplementedError("Phase 4: BriefSynthesisJudge not yet implemented.")


class GroundedAnswerJudge:
    """Stub — Phase 4 (grounded answer) not yet implemented."""

    async def score(self, document_text: str, query: str, pred: dict) -> dict:
        raise NotImplementedError("Phase 4: GroundedAnswerJudge not yet implemented.")
