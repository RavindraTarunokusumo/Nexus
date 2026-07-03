"""Cross-document relation pass — classify capsule pairs across documents."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import SemanticCapsule, SemanticRelation
from app.domain_packs.loader import DomainPack
from app.intelligence.extraction import _CANONICAL_RELATION_TYPES
from app.intelligence.lifecycle import _primary_actor
from app.intelligence.llm_client import LLMError
from app.intelligence.prompts.classify_relations import (
    SYSTEM_PROMPT,
    RelationClassification,
    build_relation_prompt,
)

__all__ = ["CrossDocReport", "classify_cross_document_relations", "build_cross_doc_pairs"]

logger = logging.getLogger(__name__)

_NON_TERMINAL_STATES = frozenset({"candidate", "active", "confirmed", "qualified"})


class CrossDocReport(BaseModel):
    candidate_pairs: int
    classified_pairs: int
    relations_created: int
    relation_ids: list[uuid.UUID]
    skipped_existing: int


@dataclass(frozen=True)
class OrderedCapsulePair:
    newer: SemanticCapsule
    older: SemanticCapsule


def _canonical_pair_key(id_a: uuid.UUID, id_b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (id_a, id_b) if id_a < id_b else (id_b, id_a)


def _newer_older(cap_a: SemanticCapsule, cap_b: SemanticCapsule) -> OrderedCapsulePair:
    if cap_a.created_at != cap_b.created_at:
        if cap_a.created_at > cap_b.created_at:
            return OrderedCapsulePair(newer=cap_a, older=cap_b)
        return OrderedCapsulePair(newer=cap_b, older=cap_a)
    if cap_a.id > cap_b.id:
        return OrderedCapsulePair(newer=cap_a, older=cap_b)
    return OrderedCapsulePair(newer=cap_b, older=cap_a)


def _pair_order_key(pair: OrderedCapsulePair) -> tuple:
    return (-pair.newer.created_at.timestamp(), str(pair.newer.id), str(pair.older.id))


def build_cross_doc_pairs(
    capsules: list[SemanticCapsule],
    existing_pair_keys: set[tuple[uuid.UUID, uuid.UUID]],
) -> tuple[list[OrderedCapsulePair], int]:
    """Group by family+actor, emit cross-document pairs, dedup, and order."""
    groups: dict[tuple[str, str], list[SemanticCapsule]] = {}
    for cap in capsules:
        actor = _primary_actor(cap.facets)
        if actor is None:
            continue
        key = (cap.object_family, actor)
        groups.setdefault(key, []).append(cap)

    pairs: list[OrderedCapsulePair] = []
    skipped = 0

    for group_caps in groups.values():
        if len(group_caps) < 2:
            continue
        for cap_a, cap_b in combinations(group_caps, 2):
            if cap_a.document_id == cap_b.document_id:
                continue
            pair_key = _canonical_pair_key(cap_a.id, cap_b.id)
            if pair_key in existing_pair_keys:
                skipped += 1
                continue
            pairs.append(_newer_older(cap_a, cap_b))

    pairs.sort(key=_pair_order_key)
    return pairs, skipped


async def classify_cross_document_relations(
    session_factory: async_sessionmaker,
    client: Any,
    *,
    domain: str,
    pack: DomainPack,
    model: str,
    max_pairs: int = 60,
    dry_run: bool = False,
) -> CrossDocReport:
    async with session_factory() as session:
        capsules = (
            (
                await session.execute(
                    select(SemanticCapsule).where(
                        SemanticCapsule.domain == domain,
                        SemanticCapsule.lifecycle_state.in_(_NON_TERMINAL_STATES),
                    )
                )
            )
            .scalars()
            .all()
        )

    cap_ids = {c.id for c in capsules}
    existing_pair_keys: set[tuple[uuid.UUID, uuid.UUID]] = set()

    if cap_ids:
        async with session_factory() as session:
            existing_rels = (
                (
                    await session.execute(
                        select(SemanticRelation).where(
                            SemanticRelation.target_thesis_id.is_(None),
                            SemanticRelation.source_capsule_id.in_(cap_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
        for rel in existing_rels:
            if rel.target_capsule_id is not None and rel.target_capsule_id in cap_ids:
                existing_pair_keys.add(
                    _canonical_pair_key(rel.source_capsule_id, rel.target_capsule_id)
                )

    pairs, skipped_existing = build_cross_doc_pairs(capsules, existing_pair_keys)
    candidate_pairs = len(pairs)

    should_classify = not dry_run and max_pairs > 0
    to_classify = pairs[:max_pairs] if should_classify else []
    classified_pairs = len(to_classify)

    relation_ids: list[uuid.UUID] = []
    relations_created = 0

    for pair in to_classify:
        cap_a = pair.newer
        cap_b = pair.older
        try:
            classification, _ = await client.complete_json(
                model=model,
                system=SYSTEM_PROMPT,
                user=build_relation_prompt(cap_a, cap_b, pack),
                response_model=RelationClassification,
                run_type="classify_relation",
            )
        except LLMError as exc:
            logger.warning(
                "Cross-doc relation classification failed (%s → %s): %s",
                cap_a.id,
                cap_b.id,
                exc,
            )
            continue

        if not classification.relation_type or classification.relation_type == "none":
            continue

        relation_id = uuid.uuid4()
        canonical_type = (
            classification.relation_type
            if classification.relation_type in _CANONICAL_RELATION_TYPES
            else "other"
        )
        domain_relation_type = (
            classification.relation_type
            if classification.relation_type not in _CANONICAL_RELATION_TYPES
            else None
        )

        async with session_factory() as session:
            session.add(
                SemanticRelation(
                    id=relation_id,
                    source_capsule_id=cap_a.id,
                    target_capsule_id=cap_b.id,
                    target_thesis_id=None,
                    relation_type=canonical_type,
                    domain_relation_type=domain_relation_type,
                    polarity=classification.polarity,
                    strength=classification.strength,
                    confidence=classification.strength,
                    evidence_capsule_ids=[],
                    rationale=classification.rationale,
                    epistemic_state={},
                    created_by_tier="t2",
                    created_by_model=model,
                )
            )
            await session.commit()

        relation_ids.append(relation_id)
        relations_created += 1

    return CrossDocReport(
        candidate_pairs=candidate_pairs,
        classified_pairs=classified_pairs,
        relations_created=relations_created,
        relation_ids=relation_ids,
        skipped_existing=skipped_existing,
    )
