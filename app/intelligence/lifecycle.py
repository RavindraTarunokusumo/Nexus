"""Deterministic lifecycle transitions for semantic capsules."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SemanticCapsule, SemanticRelation
from app.domain_packs.loader import DomainPack

_ELIGIBLE_STATES = frozenset({"candidate", "active"})

_AUTHORITY_RANK = {
    "primary": 4,
    "secondary": 3,
    "tertiary": 2,
    "unknown": 1,
}


class LifecycleTransition(BaseModel):
    capsule_id: uuid.UUID
    from_state: str
    to_state: str
    reason: str


class LifecycleReport(BaseModel):
    domain: str
    transitions: list[LifecycleTransition]
    counts: dict[str, int]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _authority_rank(epistemic_state: dict) -> int:
    auth = epistemic_state.get("source_authority", "unknown")
    return _AUTHORITY_RANK.get(auth, 1)


def _primary_actor(facets: dict) -> str | None:
    orgs = facets.get("orgs")
    if isinstance(orgs, list) and orgs:
        return str(orgs[0]).lower()
    people = facets.get("people")
    if isinstance(people, list) and people:
        return str(people[0]).lower()
    return None


def _is_supporting_relation(rel: SemanticRelation) -> bool:
    if rel.strength < 0.6:
        return False
    if rel.relation_type in ("supports", "confirms"):
        return True
    return rel.polarity == "positive"


def _check_superseded_relation(incoming: list[SemanticRelation]) -> tuple[str, str] | None:
    for rel in incoming:
        if rel.relation_type == "supersedes":
            return ("superseded", "incoming_supersedes_relation")
    return None


def _check_supersession_heuristic(
    capsule: SemanticCapsule,
    all_domain_capsules: Sequence[SemanticCapsule],
) -> tuple[str, str] | None:
    actor = _primary_actor(capsule.facets)
    if actor is None:
        return None
    for other in all_domain_capsules:
        if other.id == capsule.id:
            continue
        if other.domain != capsule.domain:
            continue
        if other.domain_object_type != capsule.domain_object_type:
            continue
        other_actor = _primary_actor(other.facets)
        if other_actor is None or other_actor != actor:
            continue
        if other.created_at > capsule.created_at:
            return ("superseded", "supersession_heuristic")
    return None


def _other_capsule_id(rel: SemanticRelation, capsule_id: uuid.UUID) -> uuid.UUID | None:
    if rel.target_capsule_id == capsule_id:
        return rel.source_capsule_id
    return rel.target_capsule_id


def _check_contradicted(
    capsule: SemanticCapsule,
    incoming: list[SemanticRelation],
    outgoing: list[SemanticRelation],
    capsule_by_id: dict[uuid.UUID, SemanticCapsule],
) -> tuple[str, str] | None:
    for rel in incoming + outgoing:
        if rel.relation_type != "contradicts":
            continue
        other_id = _other_capsule_id(rel, capsule.id)
        if other_id is None:
            continue
        other = capsule_by_id.get(other_id)
        if other is None:
            continue
        if _authority_rank(other.epistemic_state) > _authority_rank(capsule.epistemic_state):
            return ("contradicted", "higher_authority_contradiction")
    return None


def _check_qualified(incoming: list[SemanticRelation]) -> tuple[str, str] | None:
    for rel in incoming:
        if rel.relation_type == "qualifies":
            return ("qualified", "incoming_qualifies_relation")
    return None


def _check_confirmed(
    incoming: list[SemanticRelation],
    outgoing: list[SemanticRelation],
) -> tuple[str, str] | None:
    involved = incoming + outgoing
    supporting_ids = {rel.id for rel in involved if _is_supporting_relation(rel)}
    if len(supporting_ids) >= 2:
        return ("confirmed", "multiple_supporting_relations")
    return None


def _check_stale(
    capsule: SemanticCapsule, pack: DomainPack, now: datetime
) -> tuple[str, str] | None:
    policy = pack.retention_policy
    if not policy.stale_conditions:
        return None
    age = now - capsule.created_at
    if capsule.domain_object_type == "forecast" and age > timedelta(days=policy.warm_window_days):
        return ("stale", "forecast_warm_window_elapsed")
    if age > timedelta(days=policy.cold_after_days):
        return ("stale", "cold_after_days_elapsed")
    return None


def _check_archived(
    capsule: SemanticCapsule, pack: DomainPack, now: datetime
) -> tuple[str, str] | None:
    archive_days = pack.retention_policy.archive_after_days
    if archive_days is None:
        return None
    if (now - capsule.created_at) > timedelta(days=archive_days):
        return ("archived", "archive_after_days_elapsed")
    return None


def _resolve_transition(
    capsule: SemanticCapsule,
    *,
    incoming: list[SemanticRelation],
    outgoing: list[SemanticRelation],
    all_domain_capsules: Sequence[SemanticCapsule],
    capsule_by_id: dict[uuid.UUID, SemanticCapsule],
    pack: DomainPack,
    now: datetime,
) -> tuple[str, str] | None:
    checks = [
        lambda: _check_superseded_relation(incoming),
        lambda: (
            _check_supersession_heuristic(capsule, all_domain_capsules)
            if pack.retention_policy.supersession_rules
            else None
        ),
        lambda: _check_contradicted(capsule, incoming, outgoing, capsule_by_id),
        lambda: _check_qualified(incoming),
        lambda: _check_confirmed(incoming, outgoing),
        # archived before stale: archive_after_days is the longer window and the more
        # terminal state, so a capsule old enough for both must resolve to archived —
        # otherwise it sticks at stale (a non-eligible state) and is never re-evaluated.
        lambda: _check_archived(capsule, pack, now),
        lambda: _check_stale(capsule, pack, now),
    ]
    for check in checks:
        result = check()
        if result is not None:
            return result
    return None


async def apply_lifecycle_transitions(
    session: AsyncSession,
    *,
    domain: str,
    pack: DomainPack,
    now: datetime | None = None,
    dry_run: bool = False,
) -> LifecycleReport:
    """Apply deterministic lifecycle rules to candidate/active capsules in *domain*."""
    effective_now = now or _utcnow()

    eligible = (
        (
            await session.execute(
                select(SemanticCapsule).where(
                    SemanticCapsule.domain == domain,
                    SemanticCapsule.lifecycle_state.in_(_ELIGIBLE_STATES),
                )
            )
        )
        .scalars()
        .all()
    )

    all_domain = (
        (await session.execute(select(SemanticCapsule).where(SemanticCapsule.domain == domain)))
        .scalars()
        .all()
    )
    capsule_by_id = {c.id: c for c in all_domain}

    eligible_ids = [c.id for c in eligible]
    if not eligible_ids:
        return LifecycleReport(domain=domain, transitions=[], counts={})

    relations = (
        (
            await session.execute(
                select(SemanticRelation).where(
                    or_(
                        SemanticRelation.source_capsule_id.in_(eligible_ids),
                        SemanticRelation.target_capsule_id.in_(eligible_ids),
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    incoming_by_target: dict[uuid.UUID, list[SemanticRelation]] = {}
    outgoing_by_source: dict[uuid.UUID, list[SemanticRelation]] = {}
    for rel in relations:
        if rel.target_capsule_id is not None and rel.target_capsule_id in eligible_ids:
            incoming_by_target.setdefault(rel.target_capsule_id, []).append(rel)
        if rel.source_capsule_id in eligible_ids:
            outgoing_by_source.setdefault(rel.source_capsule_id, []).append(rel)

    transitions: list[LifecycleTransition] = []
    counts: dict[str, int] = {}

    for capsule in eligible:
        resolved = _resolve_transition(
            capsule,
            incoming=incoming_by_target.get(capsule.id, []),
            outgoing=outgoing_by_source.get(capsule.id, []),
            all_domain_capsules=all_domain,
            capsule_by_id=capsule_by_id,
            pack=pack,
            now=effective_now,
        )
        if resolved is None:
            continue
        to_state, reason = resolved
        transitions.append(
            LifecycleTransition(
                capsule_id=capsule.id,
                from_state=capsule.lifecycle_state,
                to_state=to_state,
                reason=reason,
            )
        )
        capsule.lifecycle_state = to_state
        capsule.updated_at = effective_now
        counts[to_state] = counts.get(to_state, 0) + 1

    if dry_run:
        await session.rollback()
    else:
        await session.commit()

    return LifecycleReport(domain=domain, transitions=transitions, counts=counts)
