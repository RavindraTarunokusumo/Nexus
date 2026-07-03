from __future__ import annotations

from pydantic import BaseModel

QUESTION_SHAPES: tuple[str, ...] = (
    "factoid",
    "multi_doc",
    "current_state",
    "conflict",
    "general",
)


class RetrievalStrategy(BaseModel):
    weight_overrides: dict[str, float] = {}
    fetch_k_multiplier: int = 3
    top_k_delta: int = 0
    answer_hint: str = ""


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
    "current_state": RetrievalStrategy(
        weight_overrides={"recency": 0.25},
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


def resolve_strategy(shape: str) -> RetrievalStrategy:
    return STRATEGIES.get(shape, STRATEGIES["general"])
