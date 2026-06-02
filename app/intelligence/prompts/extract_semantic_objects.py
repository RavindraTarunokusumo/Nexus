"""System and user prompt builders for telos-aware semantic-object extraction."""

from __future__ import annotations

from typing import get_args

from app.domain_packs.loader import DomainPack
from app.intelligence.llm_client import ClaimType, CoreType
from app.intelligence.prompts import _shared

_CORE_TYPES = ", ".join(get_args(CoreType))
_CLAIM_TYPES = ", ".join(get_args(ClaimType))

SYSTEM_PROMPT = """\
You are a telos-guided semantic compressor for an intelligence research system.

Rules:
1. Extract only the semantic objects that matter under the source's telos. Skip the rest.
2. Each object must include at least one source_ref equal to the provided segment_id.
3. Use only the listed semantic-object families and object_types. Do not invent new ones.
4. Set core_type strictly to one of the 15 listed v0.7 core types.
5. Set mvp_claim_type strictly to the claim_type the pack's mvp_claim_type table maps the chosen object_type to.
6. Set salience and confidence between 0 and 1.
7. Do not produce more objects than the per-segment budget.
8. Return strict JSON matching the SemanticExtractionOutput schema. No prose.

SemanticExtractionOutput shape:
{
  "objects": [
    {
      "source_refs": ["<segment_id>"],
      "core_type": "<one of the 15 v0.7 core types>",
      "domain_family": "<family name>",
      "domain_object_type": "<object_type from that family>",
      "function": "<one-sentence description of what this object does in context>",
      "text": "<normalized text of the extracted object>",
      "original_text": "<verbatim span from the source, or null>",
      "facets": {"orgs": ["OpenAI"], "models": ["GPT-4o"]},
      "epistemic": {
        "status": "reported",
        "source_authority": "primary",
        "confidence": 0.85,
        "evidence_quality": "medium",
        "uncertainty": null,
        "needs_escalation": false
      },
      "salience": 0.9,
      "mvp_claim_type": "<one of the 11 legacy claim types>"
    }
  ]
}
"""


def _family_lines(pack: DomainPack, applicable_names: list[str]) -> list[str]:
    """Return prompt lines for the applicable semantic-object families."""
    lines: list[str] = [
        "\n## Applicable Semantic-Object Families",
        "Use ONLY these families and their object_types:",
    ]
    for family_name in applicable_names:
        family = pack.semantic_object_families.get(family_name)
        if family is None:
            continue
        lines.append(f"\n### {family_name}")
        lines.append(f"Purpose: {family.purpose}")
        lines.append(f"Object types: {', '.join(family.object_types)}")
        mapping_parts = [f"{ot} → {ct}" for ot, ct in family.core_type_mapping.items()]
        lines.append(f"core_type_mapping: {'; '.join(mapping_parts)}")
        claim_parts = [f"{ot} → {ct}" for ot, ct in family.mvp_claim_type.items()]
        lines.append(f"mvp_claim_type: {'; '.join(claim_parts)}")
        if family.required_fields:
            lines.append(f"Required fields: {', '.join(family.required_fields)}")
    return lines


def _salience_lines(pack: DomainPack) -> list[str]:
    """Return prompt lines for the salience policy."""
    sp = pack.salience_policy
    lines: list[str] = ["\n## Salience Policy"]
    if sp.preserve_if:
        lines.append("Preserve if:")
        lines.extend(f"  + {r}" for r in sp.preserve_if)
    if sp.ignore_if:
        lines.append("Ignore if:")
        lines.extend(f"  - {r}" for r in sp.ignore_if)
    if sp.downgrade_if:
        lines.append("Downgrade if:")
        lines.extend(f"  v {r}" for r in sp.downgrade_if)
    if sp.escalate_if:
        lines.append("Escalate if (set needs_escalation: true):")
        lines.extend(f"  ^ {r}" for r in sp.escalate_if)
    return lines


def build_source_prompt_prefix(pack: DomainPack, source_type: str) -> str:
    """Build the source-static portion of the prompt (telos + families + salience + facets + budget).

    Stable across spans of the same source — safe to compute once per document.
    """
    lines: list[str] = []
    lines.append(f"\nDomain pack: {pack.metadata.pack_id} / {pack.metadata.domain}")

    lines.append("\n## Telos — Primary Purposes")
    lines.extend(f"  - {p}" for p in pack.telos.primary_purposes)
    lines.append("\n## Telos — Anti-Purposes (treat with skepticism)")
    lines.extend(f"  - {ap}" for ap in pack.telos.anti_purposes)

    profile = pack.source_type_profiles.get(source_type)
    if profile and profile.expected_semantic_families:
        applicable_names = profile.expected_semantic_families
    else:
        applicable_names = list(pack.semantic_object_families.keys())

    lines.extend(_family_lines(pack, applicable_names))
    lines.extend(_salience_lines(pack))

    fp = pack.facet_policy
    all_facets = fp.generic_facets + fp.domain_facets
    lines.append(f"\n## Facet Keys\nUse only: {', '.join(all_facets)}")

    budget = pack.budgets.max_semantic_objects_per_segment
    lines.append(f"\n## Per-Segment Budget\nDo not emit more than {budget} objects.")

    lines.append(f"\n## Valid core_type values (15)\n{_CORE_TYPES}")
    lines.append(f"\n## Valid mvp_claim_type values (11)\n{_CLAIM_TYPES}")

    return "\n".join(lines)


def build_user_prompt(
    segment_text: str,
    metadata: dict,
    pack: DomainPack | None = None,
    source_type: str | None = None,
    *,
    source_prefix: str | None = None,
) -> str:
    """Assemble a per-segment extraction prompt injecting pack-derived guidance.

    Either pass ``(pack, source_type)`` and the prefix will be built inline, OR
    pass a pre-built ``source_prefix`` from :func:`build_source_prompt_prefix`
    to avoid the O(families) rebuild on every span.

    Args:
        segment_text: The text of the segment to extract objects from.
        metadata: Must contain ``segment_id`` (str). Optional keys: ``title``,
            ``source_name``, ``published_at``, ``url``.
        pack: The loaded DomainPack for this source domain. Required when
            ``source_prefix`` is not provided.
        source_type: The source type key (e.g. ``"ai_news_article"``). Required
            when ``source_prefix`` is not provided.
        source_prefix: Pre-built static prefix from :func:`build_source_prompt_prefix`.
            When provided, ``pack`` and ``source_type`` are not used.

    Raises:
        ValueError: If ``metadata["segment_id"]`` is missing.
        ValueError: If neither ``source_prefix`` nor ``(pack, source_type)`` is provided.
    """
    if "segment_id" not in metadata:
        raise ValueError("metadata['segment_id'] is required for provenance tracking")

    if source_prefix is None:
        if pack is None or source_type is None:
            raise ValueError("Either source_prefix or both pack and source_type must be provided")
        source_prefix = build_source_prompt_prefix(pack, source_type)

    segment_id = metadata["segment_id"]
    lines: list[str] = ["Extract semantic objects from the following text segment."]
    lines.append(f"Segment ID (use exactly this value in source_refs): {segment_id}")

    if metadata.get("title"):
        lines.append(f"Article title: {metadata['title']}")
    if metadata.get("source_name"):
        lines.append(f"Source: {metadata['source_name']}")
    if metadata.get("published_at"):
        lines.append(f"Published: {metadata['published_at']}")
    if metadata.get("url"):
        lines.append(f"URL: {metadata['url']}")

    lines.append(source_prefix)
    lines.append(f"\n## Text\n{segment_text}")

    return "\n".join(lines)


def build_correction_prompt(
    original_user: str,
    invalid_response: str,
    error: str,
) -> str:
    """Append correction instructions when the model returns invalid output."""
    return _shared.build_correction_prompt(
        original_user, invalid_response, error, schema_name="SemanticExtractionOutput"
    )
