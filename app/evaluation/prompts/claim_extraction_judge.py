# app/evaluation/prompts/claim_extraction_judge.py
"""System prompt and user prompt builder for the claim extraction LLM judge."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JUDGE_SYSTEM_PROMPT = """\
You are an expert AI evaluator assessing the quality of claim extraction from news articles.

You will be given:
1. A DOCUMENT: the source text
2. A GOLD CLAIM: the reference claim (may be empty if evaluating a spurious prediction)
3. A PREDICTED CLAIM: the model's output (may be empty if evaluating a missing claim)

Evaluate the pair and return a JSON object with these fields:

- match_status (string): One of:
  - "exact"    — prediction captures the same core fact as gold with minimal paraphrase
  - "partial"  — prediction captures part of the gold claim or with significant rewording
  - "missing"  — gold claim present but prediction is empty or did not extract it
  - "spurious" — prediction is present but no gold claim exists (hallucination or over-extraction)
  - "error"    — input is malformed or evaluation is not possible

- type_correct (boolean): True if the predicted claim_type matches the gold claim_type
  (ignore this field if match_status is "missing" or "spurious" — set to false)

- groundedness (float 0.0–1.0): Fraction of the predicted claim text that is directly
  supported by the document. 1.0 = fully grounded, 0.0 = not grounded at all.
  If match_status is "missing", set to 0.0.

- factuality (float 0.0–1.0): Whether the predicted claim is factually accurate relative
  to the document. 1.0 = fully accurate, 0.0 = factually wrong.
  If match_status is "missing", set to 0.0.

- rationale (string): 1-2 sentences explaining your evaluation.

Return ONLY valid JSON. Do not include markdown fences or extra text.
"""


def build_judge_prompt(
    document_text: str,
    gold_claim: dict | None,
    pred_claim: dict | None,
) -> str:
    """Build the user-turn prompt for the claim extraction judge.

    gold_claim and pred_claim are dicts with keys: claim_text, claim_type.
    Pass None (or empty dict) when the claim is absent (missing/spurious cases).
    """
    gold_text = (gold_claim or {}).get("claim_text", "") or "(none)"
    gold_type = (gold_claim or {}).get("claim_type", "") or "(none)"
    pred_text = (pred_claim or {}).get("claim_text", "") or "(none)"
    pred_type = (pred_claim or {}).get("claim_type", "") or "(none)"

    return f"""\
DOCUMENT:
{document_text.strip()}

GOLD CLAIM:
  Text: {gold_text}
  Type: {gold_type}

PREDICTED CLAIM:
  Text: {pred_text}
  Type: {pred_type}

Evaluate this (gold, prediction) pair and return the JSON verdict.
"""


class ClaimPairVerdict(BaseModel):
    """Pydantic model for the LLM judge's verdict on a single claim pair."""

    match_status: Literal["exact", "partial", "missing", "spurious", "error"]
    type_correct: bool
    groundedness: float = Field(ge=0.0, le=1.0)
    factuality: float = Field(ge=0.0, le=1.0)
    rationale: str
