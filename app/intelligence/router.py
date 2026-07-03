from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetrievalStrategy:
    weight_overrides: dict[str, float] = field(default_factory=dict)
    fetch_k_multiplier: int = 3
    top_k_delta: int = 0
    answer_hint: str = ""


# weight_overrides merge onto pack hybrid_score_weights without renormalization:
# within one query every candidate is scored with the same weights, so scaling the
# sum is a monotone transform that cannot change ranking — only the absolute score.
STRATEGIES: dict[str, RetrievalStrategy] = {
    "factoid": RetrievalStrategy(
        weight_overrides={"semantic_similarity": 0.6, "salience": 0.05, "recency": 0.05},
        fetch_k_multiplier=6,
        answer_hint=(
            "State the specific date, number, or value asked for, taken verbatim from the evidence."
        ),
    ),
    "multi_doc": RetrievalStrategy(
        top_k_delta=3,
        fetch_k_multiplier=4,
        answer_hint="Synthesize across all relevant context blocks and cite every block you draw from.",
    ),
    # current_state deliberately has no recency override: capsule created_at is
    # ingestion order, not publication date, so boosting it buries past-dated facts
    # (T-X3 finding — it dropped release-date capsules out of top-k entirely).
    # The supersession aux blocks + answer hint carry this shape's intent instead.
    "current_state": RetrievalStrategy(
        answer_hint="Prefer the most recent superseding fact; explicitly note the fact it replaced.",
    ),
    "conflict": RetrievalStrategy(
        weight_overrides={"source_authority": 0.25, "evidence_quality": 0.25},
        answer_hint=(
            "Distinguish verified primary-source evidence from rumor or unverified reports; "
            "state the authority of your sources."
        ),
    ),
    "general": RetrievalStrategy(),
}

QUESTION_SHAPES: tuple[str, ...] = tuple(STRATEGIES)


def resolve_strategy(shape: str) -> RetrievalStrategy:
    return STRATEGIES.get(shape, STRATEGIES["general"])
