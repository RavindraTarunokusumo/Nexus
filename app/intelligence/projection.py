"""Projection layer: v0.7 SemanticObject → legacy Claim + ClaimEvidence shape."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.domain_packs.loader import DomainPack
from app.intelligence.llm_client import ClaimType, SemanticObject

logger = logging.getLogger(__name__)

__all__ = ["validate_object", "project", "enforce_budgets", "ProjectedClaim"]

# Facet keys that route to topics_json; everything else goes to entities_json.
_TOPIC_FACET_KEYS = {"domain_terms", "unknown_salient_terms"}


@dataclass(frozen=True)
class ProjectedClaim:
    claim_text: str
    claim_type: ClaimType
    entities_json: dict[str, Any]
    topics_json: dict[str, Any]
    confidence: float
    evidence_span_ids: list[str]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_object(obj: SemanticObject, pack: DomainPack) -> tuple[bool, str | None]:
    """Return (True, None) when obj is acceptable, else (False, reason)."""
    if len(obj.source_refs) == 0:
        return False, "source_refs is empty"

    floor = pack.salience_policy.min_floor
    if obj.salience < floor:
        return (
            False,
            f"salience {obj.salience} is below threshold {floor}",
        )

    family = pack.semantic_object_families.get(obj.domain_family)
    if family is None:
        return False, f"domain_family '{obj.domain_family}' not in pack"

    if obj.domain_object_type not in family.object_types:
        return (
            False,
            f"domain_object_type '{obj.domain_object_type}' not in family '{obj.domain_family}'",
        )

    expected_claim_type = family.mvp_claim_type.get(obj.domain_object_type)
    if obj.mvp_claim_type != expected_claim_type:
        return (
            False,
            (
                f"mvp_claim_type mismatch for '{obj.domain_family}/{obj.domain_object_type}': "
                f"expected '{expected_claim_type}', got '{obj.mvp_claim_type}'"
            ),
        )

    return True, None


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def project(obj: SemanticObject) -> ProjectedClaim:
    """Convert an accepted SemanticObject into a ProjectedClaim.

    Callers are responsible for calling validate_object first.
    """
    entities_json: dict[str, Any] = {}
    topics_combined: list[str] = []

    for key, values in obj.facets.items():
        if key in _TOPIC_FACET_KEYS:
            topics_combined.extend(values)
        else:
            entities_json[key] = values

    # Traceability keys
    entities_json["_function"] = (
        obj.function
    )  # internal traceability — survives without parsing _v0_7
    entities_json["_domain_family"] = (
        obj.domain_family
    )  # internal traceability — survives without parsing _v0_7

    # Forward-compat stash: full v0.7 payload for Phase B backfill
    entities_json["_v0_7"] = obj.model_dump(mode="json")

    topics_json: dict[str, Any] = {}
    if topics_combined:
        topics_json["domain_terms"] = topics_combined

    return ProjectedClaim(
        claim_text=obj.text,
        claim_type=obj.mvp_claim_type,
        entities_json=entities_json,
        topics_json=topics_json,
        confidence=obj.epistemic.confidence,
        evidence_span_ids=list(obj.source_refs),
    )


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------


def enforce_budgets(
    objects: list[SemanticObject],
    pack: DomainPack,
    source_type: str | None,
) -> list[SemanticObject]:
    """Return objects capped by pack budget rules, sorted by salience desc.

    Application order: per-segment cap is applied first (preserving the top-N
    highest-salience objects within each segment group), then the per-source cap
    (smaller of ``max_semantic_objects_per_source`` and the per-source-type
    override) is applied to the union.  All cuts use salience-descending order.
    """
    # Determine effective per-source cap
    source_cap = pack.budgets.max_semantic_objects_per_source
    if source_type is not None:
        per_type = pack.budgets.per_source_type.get(source_type, {})
        type_cap = per_type.get("max_semantic_objects_per_source")
        if type_cap is not None:
            source_cap = min(source_cap, type_cap)

    segment_cap = pack.budgets.max_semantic_objects_per_segment

    # Per-segment cap: group by first source_ref, keep top-N by salience
    by_segment: dict[str, list[SemanticObject]] = defaultdict(list)
    for obj in objects:
        segment_key = obj.source_refs[0]
        by_segment[segment_key].append(obj)

    segment_filtered: list[SemanticObject] = []
    for seg_objects in by_segment.values():
        seg_sorted = sorted(seg_objects, key=lambda o: o.salience, reverse=True)
        segment_filtered.extend(seg_sorted[:segment_cap])

    # Apply per-source cap after sorting by salience desc
    result = sorted(segment_filtered, key=lambda o: o.salience, reverse=True)
    return result[:source_cap]
