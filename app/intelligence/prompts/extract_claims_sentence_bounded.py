"""Sentence-bounded claim extraction prompt (S1).

The model receives a numbered list of sentences and must emit, per sentence,
either a single ExtractedClaim or null. This bounds output count to at most
one claim per sentence, attacking over-extraction at the architectural level.
"""

from __future__ import annotations

import re

SYSTEM_PROMPT = """\
You are a precise claim extractor.

You will receive a NUMBERED list of sentences. For EACH sentence, decide:
- If the sentence contains a single atomic factual proposition: emit one ExtractedClaim object.
- Otherwise (framing, opinion, restatement, side detail, or empty): emit null.

Rules:
- Emit AT MOST one claim per sentence. Never two.
- The claim_text MUST be a direct restatement of the proposition in that sentence — do NOT pull facts from other sentences.
- Do NOT infer, speculate, or use outside knowledge.
- Background / framing / interpretation ("marked a milestone", "is expected to") → null.

claim_type definitions:
- model_release         : A specific AI/ML model released, launched, announced, or shipped.
- benchmark_result      : A model achieves a measurable score on a named benchmark.
- product_launch        : A non-model product, feature, app, or service is released or launched.
- pricing_change        : API pricing, subscription cost, or token cost is changed or announced.
- research_finding      : A novel scientific/technical result, paper finding, or methodology.
- infrastructure_update : Compute, datacenter, hardware, cluster, or deployment infrastructure change.
- security_issue        : Vulnerability, breach, jailbreak, exploit, or safety incident.
- funding_event         : Investment round, valuation, acquisition, IPO, or major financial event.
- regulation            : Government rule, law, policy, executive order, or compliance requirement.
- forecast              : A dated prediction, projection, or roadmap commitment about the future.
- other                 : None of the above clearly applies. Use ONLY as a last resort.

Required output schema:
{
  "items": [
    {
      "sentence_index": <int matching the input number>,
      "claim": null
        OR
        {
          "claim_text": "<atomic restatement of THIS sentence's proposition>",
          "claim_type": "<one of the 11 types above>",
          "entities": ["<named entity>"],
          "topics": ["<topic keyword>"],
          "confidence": <float 0.0-1.0>,
          "rationale": "<one sentence explaining what makes this a claim>"
        }
    }
  ]
}

Output ONE entry for every input sentence index. If a sentence has no claim, set "claim": null.
"""


def split_sentences(text: str) -> list[str]:
    """Conservative sentence splitter — punctuation + whitespace, no nltk dep."""
    # Normalize whitespace.
    t = re.sub(r"\s+", " ", text).strip()
    if not t:
        return []
    # Split on .!? followed by space + uppercase or end of string.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])", t)
    return [p.strip() for p in parts if p.strip()]


def build_user_prompt(span_text: str, metadata: dict) -> str:  # noqa: ARG001
    """Build a numbered-sentence user prompt for sentence-bounded extraction."""
    sentences = split_sentences(span_text)
    if not sentences:
        return "No sentences to process."
    lines = ["Sentences:"]
    for i, s in enumerate(sentences):
        lines.append(f"[{i}] {s}")
    lines.append("")
    lines.append(
        "Return JSON matching the schema. Emit one entry per sentence (including null entries)."
    )
    return "\n".join(lines)
