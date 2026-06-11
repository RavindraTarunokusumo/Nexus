"""T2 relation-classification prompt and schema (Phase C C2).

Given two SemanticCapsule rows, asks the T2 model to classify the
semantic relationship FROM capsule A TO capsule B using the relation
types declared in the domain pack's relation_grammar.

No graph integration in this module — the classify_relations node
in extraction.py imports and calls build_relation_prompt.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.models import SemanticCapsule
from app.domain_packs.loader import DomainPack

SYSTEM_PROMPT = """\
You are a T2 semantic relation classifier for a knowledge-graph pipeline.

Given two SemanticObjects (A and B), determine the semantic relationship
FROM A TO B if one exists. Use ONLY the relation types listed in the prompt.

Rules:
1. If no meaningful relation exists, return relation_type "none".
2. polarity: "positive" when A supports or extends B; "negative" when A
   undermines or contradicts B; null for neutral or purely directional relations.
3. strength: 0.0 (negligible) to 1.0 (certain). Use 0.5 for moderate confidence.
4. Write a brief, factual rationale (one or two sentences). No prose padding.
5. Return strict JSON matching the RelationClassification schema below. No text
   outside the JSON.

RelationClassification shape:
{
  "relation_type": "supports",
  "polarity": "positive",
  "strength": 0.75,
  "rationale": "A provides empirical evidence that directly supports B's claim."
}
"""


class RelationClassification(BaseModel):
    """Response schema for the T2 relation-classification prompt."""

    relation_type: str
    polarity: str | None = None
    strength: float = Field(ge=0.0, le=1.0)
    rationale: str


def build_relation_prompt(
    cap_a: SemanticCapsule,
    cap_b: SemanticCapsule,
    pack: DomainPack,
) -> str:
    """Build the per-pair user prompt for the T2 relation classifier.

    Args:
        cap_a: Source capsule (relation is FROM A).
        cap_b: Target capsule (relation is TO B).
        pack: Loaded DomainPack — used to inject valid relation types.
    """
    all_relations = (
        list(pack.relation_grammar.core_relations)
        + list(pack.relation_grammar.domain_relations)
        + ["none"]
    )

    lines: list[str] = [
        f"Domain pack: {pack.metadata.pack_id}",
        f"Valid relation types: {', '.join(all_relations)}",
        "",
        "## Object A (source of relation)",
        f"  Family: {cap_a.object_family}  |  Type: {cap_a.domain_object_type}",
        f"  Text: {cap_a.text}",
    ]
    if cap_a.facets:
        lines.append(f"  Facets: {'; '.join(f'{k}: {v}' for k, v in cap_a.facets.items())}")

    lines += [
        "",
        "## Object B (target of relation)",
        f"  Family: {cap_b.object_family}  |  Type: {cap_b.domain_object_type}",
        f"  Text: {cap_b.text}",
    ]
    if cap_b.facets:
        lines.append(f"  Facets: {'; '.join(f'{k}: {v}' for k, v in cap_b.facets.items())}")

    lines += [
        "",
        "Return a RelationClassification JSON object.",
        "Do not include any text outside the JSON object.",
    ]
    return "\n".join(lines)
