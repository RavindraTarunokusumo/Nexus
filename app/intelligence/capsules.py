"""Shared capsule assembly: idempotency key, embedder singleton, and row builder.

Both the live extraction path (``app/intelligence/extraction.py::store_claims``)
and the backfill path (``app/intelligence/backfill.py::capsule_from_claim``)
funnel through ``build_capsule_row`` so the mapping from a ``SemanticObject``
to ``SemanticCapsule`` + ``CapsuleSegment`` rows lives in exactly one place.
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from app.db.models import CapsuleSegment, SemanticCapsule
from app.intelligence.embedder import Embedder
from app.intelligence.llm_client import SemanticObject

logger = logging.getLogger(__name__)

__all__ = [
    "get_embedder",
    "build_capsule_idempotency_key",
    "build_capsule_row",
]

# claim_evidence.evidence_role vocabulary → capsule_segments.role CHECK vocabulary
# (ck_capsule_segments_role: grounds/supports/contradicts/qualifies/refines/exemplifies/other).
_EVIDENCE_ROLE_TO_SEGMENT_ROLE = {"support": "supports", "refute": "contradicts"}


# Module-level embedder singleton. Lazy-init on first use so test environments
# that never assemble capsules don't pay the model-load cost. The FastAPI
# lifespan uses its own Embedder on app.state; extraction/backfill run as
# background work with no request context, so we keep a separate process-level
# instance here.
_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def build_capsule_idempotency_key(
    *,
    document_id: uuid.UUID | str,
    source_refs: list[str],
    domain_object_type: str,
    text: str,
) -> str:
    """Deterministic UNIQUE key for SemanticCapsule rows.

    Formula:
        {document_id}:{','.join(sorted(source_refs))}:{domain_object_type}:{sha256(text)[:16]}

    Rationale for the column choices (B2 review):
    - `document_id`: scopes uniqueness to a single document.
    - `sorted(source_refs)`: identical objects from the same evidence
      spans collapse into one capsule regardless of ref ordering.
    - `domain_object_type` (not `core_type`): strictly more specific
      than `core_type`, so two different domain_object_types that
      share a core_type stay distinct.
    - `sha256(text)[:16]`: 64-bit content fingerprint; strictly
      stronger than `sha1[:8]` (which plan §6 listed but never
      hard-mandated). Same determinism, lower collision risk.

    B3 (backfill) MUST import this function rather than recompute
    the formula independently.
    """
    refs_csv = ",".join(sorted(source_refs))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{document_id}:{refs_csv}:{domain_object_type}:{digest}"


def build_capsule_row(
    *,
    capsule_id: uuid.UUID,
    source_id: uuid.UUID | None,
    document_id: uuid.UUID,
    claim_id: uuid.UUID,
    obj: SemanticObject,
    domain: str,
    source_telos: str | None,
    embedding: list[float],
    created_by_tier: str,
    created_by_model: str | None,
    lifecycle_state: str = "active",
    evidence_roles: dict[uuid.UUID, str] | None = None,
    created_at=None,
    updated_at=None,
) -> tuple[SemanticCapsule, list[CapsuleSegment]]:
    """Build a SemanticCapsule + N CapsuleSegment rows from a live SemanticObject.

    Single source of truth for the SemanticObject → capsule-column mapping.
    Used by both extraction.store_claims (live path) and backfill.capsule_from_claim
    (recovery path).

    ``evidence_roles`` maps span_id → role; values in the ``claim_evidence``
    vocabulary ("support"/"refute") are translated to the ``capsule_segments.role``
    CHECK vocabulary via ``_EVIDENCE_ROLE_TO_SEGMENT_ROLE``; missing spans fall back
    to "grounds" (the column default). Already-valid segment roles pass through.
    ``created_at``/``updated_at`` default to None (DB defaults); backfill passes
    the claim's original created_at to preserve provenance ordering.
    """
    roles = evidence_roles or {}

    idempotency_key = build_capsule_idempotency_key(
        document_id=document_id,
        source_refs=obj.source_refs,
        domain_object_type=obj.domain_object_type,
        text=obj.text,
    )
    escalation_state = "flagged" if obj.epistemic.needs_escalation else "none"

    capsule_kwargs: dict = dict(
        id=capsule_id,
        source_id=source_id,
        document_id=document_id,
        claim_id=claim_id,
        idempotency_key=idempotency_key,
        core_type=obj.core_type,
        text=obj.text,
        domain=domain,
        source_telos=source_telos,
        object_family=obj.domain_family,
        domain_object_type=obj.domain_object_type,
        function=obj.function,
        facets=obj.facets,
        epistemic_state=obj.epistemic.model_dump(mode="json"),
        salience=obj.salience,
        confidence=obj.epistemic.confidence,
        lifecycle_state=lifecycle_state,
        escalation_state=escalation_state,
        embedding=embedding,
        created_by_tier=created_by_tier,
        created_by_model=created_by_model,
    )
    if created_at is not None:
        capsule_kwargs["created_at"] = created_at
    if updated_at is not None:
        capsule_kwargs["updated_at"] = updated_at

    capsule = SemanticCapsule(**capsule_kwargs)

    segments: list[CapsuleSegment] = []
    for ref in obj.source_refs:
        if isinstance(ref, str):
            try:
                span_uuid = uuid.UUID(ref)
            except ValueError:
                # LLM occasionally echoes a non-UUID span ref (same class as the
                # extraction.py evidence guard); drop the segment, keep the capsule.
                logger.warning("Skipping non-UUID source ref %r", ref)
                continue
        else:
            span_uuid = ref
        raw_role = roles.get(span_uuid, "grounds")
        role = _EVIDENCE_ROLE_TO_SEGMENT_ROLE.get(raw_role, raw_role)
        segments.append(
            CapsuleSegment(
                capsule_id=capsule_id,
                segment_id=span_uuid,
                role=role,
            )
        )

    return capsule, segments
