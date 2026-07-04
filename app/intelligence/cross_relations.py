"""Cross-document relation pass — classify capsule pairs across documents."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from typing import Any

from pydantic import BaseModel, computed_field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Document, SemanticCapsule, SemanticRelation
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
    relation_ids: list[uuid.UUID]
    skipped_existing: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def relations_created(self) -> int:
        return len(self.relation_ids)


@dataclass(frozen=True)
class OrderedCapsulePair:
    newer: SemanticCapsule
    older: SemanticCapsule


def _canonical_pair_key(id_a: uuid.UUID, id_b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (id_a, id_b) if id_a < id_b else (id_b, id_a)


def _newer_older(
    cap_a: SemanticCapsule,
    cap_b: SemanticCapsule,
    ts: Callable[[SemanticCapsule], datetime],
) -> OrderedCapsulePair:
    if ts(cap_a) != ts(cap_b):
        if ts(cap_a) > ts(cap_b):
            return OrderedCapsulePair(newer=cap_a, older=cap_b)
        return OrderedCapsulePair(newer=cap_b, older=cap_a)
    if cap_a.id > cap_b.id:
        return OrderedCapsulePair(newer=cap_a, older=cap_b)
    return OrderedCapsulePair(newer=cap_b, older=cap_a)


def build_cross_doc_pairs(
    capsules: list[SemanticCapsule],
    existing_pair_keys: set[tuple[uuid.UUID, uuid.UUID]],
    effective_ts: dict[uuid.UUID, datetime] | None = None,
) -> tuple[list[OrderedCapsulePair], int]:
    """Group by family+actor, emit cross-document pairs, dedup, and order.

    effective_ts maps capsule id -> document publication time; capsules absent from
    the map fall back to created_at (ingestion time). Direction and priority follow
    the effective timestamp so ingestion order can't invert supersedes edges.
    """

    def ts(cap: SemanticCapsule) -> datetime:
        return (effective_ts or {}).get(cap.id) or cap.created_at

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
            pairs.append(_newer_older(cap_a, cap_b, ts))

    pairs.sort(key=lambda p: (-ts(p.newer).timestamp(), str(p.newer.id), str(p.older.id)))
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
    existing_pair_keys: set[tuple[uuid.UUID, uuid.UUID]] = set()
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(SemanticCapsule, Document.published_at)
                .join(Document, SemanticCapsule.document_id == Document.id)
                .where(
                    SemanticCapsule.domain == domain,
                    SemanticCapsule.lifecycle_state.in_(_NON_TERMINAL_STATES),
                )
            )
        ).all()
        capsules = [cap for cap, _ in rows]
        effective_ts = {cap.id: published for cap, published in rows if published is not None}
        cap_ids = {c.id for c in capsules}
        if cap_ids:
            existing_rels = (
                (
                    await session.execute(
                        select(SemanticRelation).where(
                            SemanticRelation.target_thesis_id.is_(None),
                            SemanticRelation.source_capsule_id.in_(cap_ids),
                            SemanticRelation.target_capsule_id.in_(cap_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            existing_pair_keys = {
                _canonical_pair_key(rel.source_capsule_id, rel.target_capsule_id)
                for rel in existing_rels
            }

    pairs, skipped_existing = build_cross_doc_pairs(capsules, existing_pair_keys, effective_ts)
    candidate_pairs = len(pairs)

    to_classify = pairs[:max_pairs] if not dry_run and max_pairs > 0 else []
    classified_pairs = len(to_classify)

    relation_ids: list[uuid.UUID] = []
    semaphore = asyncio.Semaphore(4)

    async def classify_pair(pair):
        cap_a = pair.newer
        cap_b = pair.older
        async with semaphore:
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
                return None
            return pair, classification

    classifications = await asyncio.gather(*[classify_pair(p) for p in to_classify])

    for item in classifications:
        if item is None:
            continue
        pair, classification = item
        cap_a = pair.newer
        cap_b = pair.older

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

    return CrossDocReport(
        candidate_pairs=candidate_pairs,
        classified_pairs=classified_pairs,
        relation_ids=relation_ids,
        skipped_existing=skipped_existing,
    )
