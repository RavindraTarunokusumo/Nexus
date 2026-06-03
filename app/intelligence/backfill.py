"""B3 — Backfill SemanticCapsule + CapsuleSegment from Phase-A _v0_7 blobs.

Reads existing Claim.entities_json["_v0_7"] payloads (the forward-compat
stash Phase A's projection left behind) and constructs SemanticCapsule +
CapsuleSegment rows for every Phase-A-produced claim.

Idempotency contract:
  - Uses the shared build_capsule_idempotency_key from projection.py.
  - Checks for existence BEFORE attempting INSERT to avoid IntegrityError noise.
  - Re-runs produce zero new writes when all capsules already exist.

Embeddings are generated at write time via the same bge-small-en-v1.5
singleton used by extraction.py — one embedder per process.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from app.db.models import CapsuleSegment, Claim, Document, SemanticCapsule, Source
from app.domain_packs.loader import load_pack
from app.intelligence.extraction import _get_embedder
from app.intelligence.projection import build_capsule_idempotency_key

logger = logging.getLogger(__name__)


@dataclass
class BackfillResult:
    claims_scanned: int = 0
    claims_skipped_no_v07: int = 0
    claims_skipped_already_backfilled: int = 0
    capsules_written: int = 0
    capsule_segments_written: int = 0
    errors: list[str] = field(default_factory=list)


def capsule_from_claim(
    claim: Claim,
    source_id: uuid.UUID,
    domain: str,
    source_telos: str | None,
    embedding: list[float],
    evidence_roles: dict[uuid.UUID, str],
) -> tuple[SemanticCapsule, list[CapsuleSegment]]:
    """Pure function: build SemanticCapsule + CapsuleSegment rows from a Claim row.

    Reads claim.entities_json["_v0_7"] for all semantic fields.
    The caller is responsible for verifying the _v0_7 key exists before calling.

    ``evidence_roles`` maps span_id → evidence_role from the existing ClaimEvidence
    rows for this claim; used to set CapsuleSegment.role. Falls back to "support"
    (what Phase A always writes) when a span_id has no matching ClaimEvidence row.
    Pass ``{}`` when no evidence-role data is available.

    Field mapping mirrors store_claims in extraction.py line-for-line so both
    paths produce identical rows for identical inputs.
    """
    ej: dict = claim.entities_json  # type: ignore[assignment]  # caller guarantees non-None
    v07: dict = ej["_v0_7"]

    text_value: str = v07["text"]
    core_type: str = v07["core_type"]
    domain_object_type: str = v07["domain_object_type"]
    source_refs: list[str] = v07.get("source_refs", [])

    idempotency_key = build_capsule_idempotency_key(
        document_id=claim.document_id,
        source_refs=source_refs,
        domain_object_type=domain_object_type,
        text=text_value,
    )

    # Deterministic capsule UUID so re-runs produce the same PK.
    capsule_id = uuid.uuid5(uuid.NAMESPACE_OID, idempotency_key)

    epistemic: dict = v07.get("epistemic", {})
    needs_escalation = epistemic.get("needs_escalation", False)
    escalation_state = "flagged" if needs_escalation else "none"

    # lifecycle_state mirrors Claim.status
    status_map = {"active": "active", "rejected": "rejected"}
    lifecycle_state = status_map.get(claim.status or "active", "active")

    capsule = SemanticCapsule(
        id=capsule_id,
        source_id=source_id,
        document_id=claim.document_id,
        claim_id=claim.id,
        idempotency_key=idempotency_key,
        core_type=core_type,
        text=text_value,
        domain=domain,
        source_telos=source_telos,
        object_family=v07.get("domain_family") or ej.get("_domain_family", ""),
        domain_object_type=domain_object_type,
        function=v07.get("function") or ej.get("_function"),
        facets=v07.get("facets", {}),
        epistemic_state=epistemic,
        salience=v07.get("salience", 0.5),
        confidence=epistemic.get("confidence", claim.confidence or 0.5),
        lifecycle_state=lifecycle_state,
        escalation_state=escalation_state,
        embedding=embedding,
        created_by_tier="backfill",
        created_by_model=None,
        created_at=claim.created_at,
        updated_at=claim.created_at,
    )

    segments = []
    for ref in source_refs:
        span_uuid = uuid.UUID(ref) if isinstance(ref, str) else ref
        role = evidence_roles.get(span_uuid, "support")
        segments.append(
            CapsuleSegment(
                capsule_id=capsule_id,
                segment_id=span_uuid,
                role=role,
            )
        )

    return capsule, segments


def _build_candidate_keys(
    to_process: list[tuple[Claim, uuid.UUID, str]],
) -> list[str]:
    """Compute idempotency keys for every claim in the batch."""
    keys: list[str] = []
    for claim, _source_id, _domain_pack in to_process:
        ej_checked: dict = claim.entities_json  # type: ignore[assignment]  # guarded above
        v07 = ej_checked["_v0_7"]
        keys.append(
            build_capsule_idempotency_key(
                document_id=claim.document_id,
                source_refs=v07.get("source_refs", []),
                domain_object_type=v07.get("domain_object_type", ""),
                text=v07.get("text", ""),
            )
        )
    return keys


def _filter_new(
    to_process: list[tuple[Claim, uuid.UUID, str]],
    candidate_keys: list[str],
    existing_keys: set[str],
    result: BackfillResult,
) -> tuple[list[tuple[Claim, uuid.UUID, str]], list[str]]:
    """Drop claims whose idempotency key already exists; return lists of new items and texts."""
    new_claims_info: list[tuple[Claim, uuid.UUID, str]] = []
    new_texts: list[str] = []
    for (claim, source_id, domain_pack), key in zip(to_process, candidate_keys, strict=False):
        if key in existing_keys:
            result.claims_skipped_already_backfilled += 1
            continue
        new_claims_info.append((claim, source_id, domain_pack))
        ej_inner: dict = claim.entities_json  # type: ignore[assignment]  # guarded
        new_texts.append(ej_inner["_v0_7"].get("text", ""))
    return new_claims_info, new_texts


async def _write_batch(
    session_factory: async_sessionmaker,
    new_claims_info: list[tuple[Claim, uuid.UUID, str]],
    embeddings: list[list[float]],
    result: BackfillResult,
    dry_run: bool,
) -> None:
    """Embed text in one batch, call capsule_from_claim, session.add_all, then
    commit or rollback per dry_run flag."""
    telos_cache: dict[str, str | None] = {}

    async with session_factory() as session:
        rows_to_add: list = []
        for (claim, source_id, domain_pack), embedding in zip(
            new_claims_info, embeddings, strict=False
        ):
            if domain_pack not in telos_cache:
                try:
                    pack = load_pack(domain_pack)
                    telos_cache[domain_pack] = (
                        pack.telos.primary_purposes[0] if pack.telos.primary_purposes else None
                    )
                except Exception as exc:
                    logger.warning("Could not load pack %r: %s", domain_pack, exc)
                    telos_cache[domain_pack] = None

            source_telos = telos_cache[domain_pack]

            evidence_roles: dict[uuid.UUID, str] = {
                ev.span_id: ev.evidence_role
                for ev in (claim.evidence_links or [])
                if ev.evidence_role is not None
            }
            try:
                capsule, segments = capsule_from_claim(
                    claim,
                    source_id=source_id,
                    domain=domain_pack,
                    source_telos=source_telos,
                    embedding=embedding,
                    evidence_roles=evidence_roles,
                )
            except Exception as exc:
                msg = f"claim {claim.id}: {exc}"
                logger.warning("Backfill error for %s", msg)
                result.errors.append(msg)
                continue

            rows_to_add.append(capsule)
            rows_to_add.extend(segments)
            result.capsules_written += 1
            result.capsule_segments_written += len(segments)

        if rows_to_add:
            session.add_all(rows_to_add)
            if dry_run:
                await session.rollback()
            else:
                await session.commit()


async def backfill_capsules(
    session_factory: async_sessionmaker,
    *,
    dry_run: bool = False,
    batch_size: int = 500,
) -> BackfillResult:
    """Iterate all Claims, build capsules from _v0_7 blobs, write rows idempotently.

    Args:
        session_factory: async_sessionmaker bound to the target DB.
        dry_run: if True, roll back each batch instead of committing.
        batch_size: number of claims to load per page query.

    Returns:
        BackfillResult with counts of what was (or would be) written.
    """
    result = BackfillResult()
    embedder = _get_embedder()
    offset = 0

    while True:
        # Load a page of claims joined to their document for source_id.
        # Eager-load evidence_links so capsule_from_claim can build the
        # span_id → evidence_role lookup without additional queries.
        async with session_factory() as session:
            stmt = (
                select(Claim, Document.source_id, Source.domain_pack)
                .join(Document, Claim.document_id == Document.id)
                .join(Source, Document.source_id == Source.id)
                .options(selectinload(Claim.evidence_links))
                .order_by(Claim.created_at)
                .limit(batch_size)
                .offset(offset)
            )
            rows = (await session.execute(stmt)).all()

        if not rows:
            break

        result.claims_scanned += len(rows)
        offset += len(rows)

        # Partition into "need processing" vs "skip — no _v0_7".
        to_process: list[tuple[Claim, uuid.UUID, str]] = []
        for claim, source_id, domain_pack in rows:
            ej = claim.entities_json
            if not ej or "_v0_7" not in ej:
                result.claims_skipped_no_v07 += 1
                continue
            to_process.append((claim, source_id, domain_pack))

        if not to_process:
            continue

        # Batch-check which idempotency keys already exist.
        candidate_keys = _build_candidate_keys(to_process)

        async with session_factory() as session:
            existing_stmt = select(SemanticCapsule.idempotency_key).where(
                SemanticCapsule.idempotency_key.in_(candidate_keys)
            )
            existing_keys: set[str] = set((await session.execute(existing_stmt)).scalars().all())

        new_claims_info, new_texts = _filter_new(to_process, candidate_keys, existing_keys, result)

        if not new_claims_info:
            continue

        # Embed all texts in one batch call.
        embeddings: list[list[float]] = embedder.embed(new_texts)

        await _write_batch(session_factory, new_claims_info, embeddings, result, dry_run)

        if len(rows) < batch_size:
            # Last page — no more claims.
            break

    # For dry_run, the "written" counts reflect what WOULD be written; reset DB state
    # has already been handled by rollback above.
    return result
