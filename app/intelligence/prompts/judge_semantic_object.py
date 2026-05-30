"""System prompt and schema for the T2 semantic-object evidence-sufficiency judge (A7).

This module is a scaffold only — no graph integration yet.  Escalation has no
home table until Phase B; this surface exists so a later commit can wire it in
behind a feature flag without touching the prompt text.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain_packs.loader import DomainPack
from app.intelligence.llm_client import SemanticObject

SYSTEM_PROMPT = """\
You are a T2 evidence-sufficiency judge for a semantic-intelligence pipeline.

Given a SemanticObject extracted from a source segment, decide whether the
object has sufficient evidence to be trusted at its stated confidence, and
whether it should be escalated for human or higher-tier review.

Rules:
1. Read the object's text, function, facets, and epistemic state carefully.
2. Evaluate whether the evidence_quality and confidence are mutually consistent.
3. Apply any family-specific status_rules and escalation_policy supplied below.
4. Set evidence_sufficient to false if the object's confidence exceeds what the
   cited evidence can support (e.g. speculative claim rated 0.9).
5. Set recommended_confidence to the confidence you would assign given the
   evidence actually present; keep it between 0.0 and 1.0.
6. Set escalate to true whenever the object conflicts with known facts, contains
   numeric contradictions, or the escalation_policy rules are triggered.
7. Write a brief, factual rationale (one or two sentences). No prose padding.
8. Return strict JSON matching the JudgeVerdict schema. No prose outside JSON.

JudgeVerdict shape:
{
  "evidence_sufficient": true,
  "recommended_confidence": 0.75,
  "escalate": false,
  "rationale": "Evidence quality matches stated confidence; no conflicts."
}
"""


class JudgeVerdict(BaseModel):
    """Response schema the judge prompt asks the model to return."""

    evidence_sufficient: bool
    recommended_confidence: float = Field(ge=0.0, le=1.0)
    escalate: bool
    rationale: str


def build_judge_prompt(obj: SemanticObject, pack: DomainPack) -> str:
    """Build the per-object user prompt for the T2 evidence-sufficiency judge.

    Args:
        obj:  The SemanticObject to evaluate.
        pack: The loaded DomainPack for this source domain; used to inject
              family-specific epistemic rules (status_rules, escalation_policy).
    """
    lines: list[str] = [
        f"Domain pack: {pack.metadata.pack_id}",
        f"Object family: {obj.domain_family}  |  type: {obj.domain_object_type}",
        f"Function: {obj.function}",
        f"Text: {obj.text}",
    ]

    if obj.facets:
        facet_parts = "; ".join(f"{k}: {v}" for k, v in obj.facets.items())
        lines.append(f"Facets: {facet_parts}")

    ep = obj.epistemic
    lines.append(
        f"Epistemic: status={ep.status}  authority={ep.source_authority}"
        f"  confidence={ep.confidence}  evidence_quality={ep.evidence_quality}"
        f"  needs_escalation={ep.needs_escalation}"
    )
    if ep.uncertainty:
        lines.append(f"Uncertainty note: {ep.uncertainty}")

    ep_policy = pack.epistemic_policy
    status_rules = ep_policy.status_rules.get(obj.domain_family)
    escalation_policy = ep_policy.escalation_policy.get(obj.domain_family)

    if status_rules or escalation_policy:
        lines.append("\n## Family-Specific Epistemic Rules")
        if status_rules:
            lines.append(f"status_rules: {status_rules}")
        if escalation_policy:
            lines.append(f"escalation_policy: {escalation_policy}")

    lines.append(
        "\nReturn a JudgeVerdict JSON object. " "Do not include any text outside the JSON object."
    )

    return "\n".join(lines)
