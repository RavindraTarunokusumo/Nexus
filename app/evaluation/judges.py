# app/evaluation/judges.py
"""LLM-as-a-Judge evaluators for each pipeline output type."""

from __future__ import annotations

import asyncio
from typing import Any

from app.evaluation.metrics import align_semantic_objects
from app.evaluation.prompts.semantic_object_judge import (
    JUDGE_SYSTEM_PROMPT,
    SemanticObjectPairVerdict,
    build_judge_prompt,
)


class SemanticObjectJudge:
    """LLM judge for v0.7 semantic-object extraction quality.

    Aligns predicted semantic objects to gold objects by Jaccard similarity on
    the `text` field, then calls the LLM to score each (gold, pred) pair on
    mvp_claim_type, core_type, domain_family alignment plus a capsule
    completeness rubric over facets/epistemic/salience.
    """

    name: str = "semantic_object_judge_v1"

    def __init__(self, model: str, llm_client: Any) -> None:
        self._model = model
        self._llm_client = llm_client

    async def score(
        self,
        document_text: str,
        gold_objects: list[dict],
        pred_objects: list[dict],
    ) -> dict:
        """Score predicted semantic objects against gold.

        Returns a dict with:
            precision, recall, f1                       — set-level on matched pairs
            mvp_claim_type_projection_accuracy          — fraction of matched pairs
                                                          with correct mvp_claim_type
            core_type_accuracy                          — fraction with correct core_type
            domain_family_accuracy                      — fraction with correct domain_family
            mean_groundedness, mean_factuality          — averages over matched pairs
            mean_capsule_completeness                   — capsule-only metric averaged
                                                          over predicted (matched) pairs
            salience_precision                          — average predicted salience
                                                          over matched pairs (proxy
                                                          for capsule signal quality)
            per_pair_verdicts                           — per-pair verdict dicts
        """
        pairs = align_semantic_objects(gold_objects, pred_objects)

        judgments = await asyncio.gather(
            *[self._judge_pair(document_text, gold, pred) for gold, pred in pairs]
        )

        n_matched = 0
        per_pair: list[dict] = []
        mvp_correct: list[bool] = []
        core_correct: list[bool] = []
        family_correct: list[bool] = []
        groundedness_scores: list[float] = []
        factuality_scores: list[float] = []
        completeness_scores: list[float] = []
        matched_pred_salience: list[float] = []
        total_judge_tokens: int = 0

        for (_gold, pred), (verdict, tokens) in zip(pairs, judgments, strict=True):
            total_judge_tokens += tokens
            per_pair.append(verdict)
            if verdict["match_status"] in ("exact", "partial"):
                n_matched += 1
                mvp_correct.append(bool(verdict["mvp_claim_type_correct"]))
                core_correct.append(bool(verdict["core_type_correct"]))
                family_correct.append(bool(verdict["domain_family_correct"]))
                groundedness_scores.append(verdict["groundedness"])
                factuality_scores.append(verdict["factuality"])
                completeness_scores.append(verdict["capsule_completeness"])
                if pred is not None:
                    matched_pred_salience.append(float(pred.get("salience", 0.0)))

        n_gold = len(gold_objects)
        n_pred = len(pred_objects)

        precision = n_matched / n_pred if n_pred > 0 else 0.0
        recall = n_matched / n_gold if n_gold > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        if n_gold == 0 and n_pred == 0:
            precision = recall = f1 = 1.0

        def _mean(xs: list[float] | list[bool]) -> float:
            return sum(xs) / len(xs) if xs else 0.0

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "mvp_claim_type_projection_accuracy": round(_mean(mvp_correct), 4),
            "core_type_accuracy": round(_mean(core_correct), 4),
            "domain_family_accuracy": round(_mean(family_correct), 4),
            "mean_groundedness": round(_mean(groundedness_scores), 4),
            "mean_factuality": round(_mean(factuality_scores), 4),
            "mean_capsule_completeness": round(_mean(completeness_scores), 4),
            "salience_precision": round(_mean(matched_pred_salience), 4),
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

        Returns a (verdict_dict, token_count) tuple. Tokens are 0 on error
        or when the LLM call is skipped (both gold and pred are None).
        """
        if gold is None and pred is None:
            return {
                "match_status": "error",
                "mvp_claim_type_correct": False,
                "core_type_correct": False,
                "domain_family_correct": False,
                "groundedness": 0.0,
                "factuality": 0.0,
                "capsule_completeness": 0.0,
                "rationale": "Both gold and pred are None — alignment error.",
            }, 0

        user_prompt = build_judge_prompt(document_text, gold, pred)
        try:
            verdict, tokens = await self._llm_client.complete_json(
                model=self._model,
                system=JUDGE_SYSTEM_PROMPT,
                user=user_prompt,
                response_model=SemanticObjectPairVerdict,
                temperature=0.0,
            )
            return verdict.model_dump(), tokens
        except Exception as exc:  # noqa: BLE001
            return {
                "match_status": "error",
                "mvp_claim_type_correct": False,
                "core_type_correct": False,
                "domain_family_correct": False,
                "groundedness": 0.0,
                "factuality": 0.0,
                "capsule_completeness": 0.0,
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
