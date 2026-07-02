"""Thesis writer: build_thesis_row (pure) + synthesize_theses_from_relations (DB orchestration).

Mirrors app/intelligence/capsules.py's build_capsule_row pattern. Per
docs/superpowers/specs/2026-07-02-phase-c-remainder-design.md, this is a
standalone writer with no automatic trigger — Phase E's consolidation worker
owns deciding when theses get created; this module only owns constructing
schema-valid rows and clustering existing relations into candidate theses.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SemanticCapsule, SemanticRelation, Thesis
from app.intelligence.tiers import validate_writer_tier

__all__ = ["build_thesis_row", "synthesize_theses_from_relations"]


def build_thesis_row(
    *,
    thesis_id: uuid.UUID,
    domain: str,
    thesis_type: str,
    statement: str,
    supporting_capsule_ids: list[uuid.UUID],
    contradicting_capsule_ids: list[uuid.UUID],
    confidence: float,
    created_by_tier: str,
    title: str | None = None,
) -> Thesis:
    validate_writer_tier(created_by_tier)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be in [0, 1], got {confidence!r}")
    return Thesis(
        id=thesis_id,
        domain=domain,
        thesis_type=thesis_type,
        title=title,
        statement=statement,
        supporting_capsule_ids=supporting_capsule_ids,
        contradicting_capsule_ids=contradicting_capsule_ids,
        confidence=confidence,
        created_by_tier=created_by_tier,
    )


def _find(parent: dict[uuid.UUID, uuid.UUID], x: uuid.UUID) -> uuid.UUID:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: dict[uuid.UUID, uuid.UUID], a: uuid.UUID, b: uuid.UUID) -> None:
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb:
        parent[ra] = rb


def _filter_domain_binary_relations(
    relations: list[SemanticRelation],
    domain_capsule_ids: set[uuid.UUID],
) -> list[SemanticRelation]:
    filtered: list[SemanticRelation] = []
    for r in relations:
        target_id = r.target_capsule_id
        if target_id is None:
            continue
        if r.source_capsule_id in domain_capsule_ids and target_id in domain_capsule_ids:
            filtered.append(r)
    return filtered


def _cluster_capsule_ids(relations: list[SemanticRelation]) -> dict[uuid.UUID, set[uuid.UUID]]:
    parent: dict[uuid.UUID, uuid.UUID] = {}
    for r in relations:
        target_id = r.target_capsule_id
        if target_id is None:
            continue
        parent.setdefault(r.source_capsule_id, r.source_capsule_id)
        parent.setdefault(target_id, target_id)
        _union(parent, r.source_capsule_id, target_id)

    components: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for cid in parent:
        components[_find(parent, cid)].add(cid)
    return components


def _thesis_from_cluster(
    *,
    member_ids: set[uuid.UUID],
    relations: list[SemanticRelation],
    caps_by_id: dict[uuid.UUID, SemanticCapsule],
    domain: str,
    min_cluster_size: int,
    created_by_tier: str,
) -> Thesis | None:
    if len(member_ids) < min_cluster_size:
        return None
    members = [caps_by_id[m] for m in member_ids if m in caps_by_id]
    if len(members) < min_cluster_size:
        return None

    contradicting: set[uuid.UUID] = set()
    component_edges = [
        r for r in relations if {r.source_capsule_id, r.target_capsule_id} <= member_ids
    ]
    for r in component_edges:
        target_id = r.target_capsule_id
        if target_id is None:
            continue
        if r.polarity == "negative" or r.relation_type == "contradicts":
            contradicting.add(r.source_capsule_id)
            contradicting.add(target_id)
    supporting = member_ids - contradicting

    anchor = max(members, key=lambda c: c.salience)
    confidence = sum(r.confidence for r in component_edges) / len(component_edges)

    return build_thesis_row(
        thesis_id=uuid.uuid4(),
        domain=domain,
        thesis_type=anchor.object_family,
        statement=anchor.text,
        supporting_capsule_ids=sorted(supporting, key=str),
        contradicting_capsule_ids=sorted(contradicting, key=str),
        confidence=min(max(confidence, 0.0), 1.0),
        created_by_tier=created_by_tier,
    )


async def synthesize_theses_from_relations(
    session: AsyncSession,
    *,
    domain: str,
    min_strength: float = 0.6,
    min_cluster_size: int = 2,
    created_by_tier: str = "t2",
    dry_run: bool = False,
) -> list[Thesis]:
    """Cluster same-family capsules connected by strong binary relations into Thesis rows.

    Binary relations only (both source and target capsule set — excludes
    judge_capsules' unary self-reference rows). Capsules are only ever
    related within a single object_family (classify_relations only pairs
    same-family capsules), so thesis_type = the shared family is a
    restatement of an existing invariant, not new clustering logic.
    """
    domain_capsules_result = await session.execute(
        select(SemanticCapsule).where(SemanticCapsule.domain == domain)
    )
    domain_capsule_by_id = {c.id: c for c in domain_capsules_result.scalars().all()}
    domain_capsule_ids = set(domain_capsule_by_id.keys())

    relations_result = await session.execute(
        select(SemanticRelation).where(
            SemanticRelation.target_capsule_id.is_not(None),
            SemanticRelation.strength >= min_strength,
            SemanticRelation.source_capsule_id.in_(domain_capsule_ids),
        )
    )
    relations = _filter_domain_binary_relations(
        list(relations_result.scalars().all()),
        domain_capsule_ids,
    )
    if not relations:
        return []

    components = _cluster_capsule_ids(relations)
    cluster_capsule_ids = {cid for members in components.values() for cid in members}
    caps_by_id = {
        cid: domain_capsule_by_id[cid] for cid in cluster_capsule_ids if cid in domain_capsule_by_id
    }

    theses: list[Thesis] = []
    for member_ids in components.values():
        thesis = _thesis_from_cluster(
            member_ids=member_ids,
            relations=relations,
            caps_by_id=caps_by_id,
            domain=domain,
            min_cluster_size=min_cluster_size,
            created_by_tier=created_by_tier,
        )
        if thesis is not None:
            theses.append(thesis)

    if theses:
        session.add_all(theses)
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    return theses
