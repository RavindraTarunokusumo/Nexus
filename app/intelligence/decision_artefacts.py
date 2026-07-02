"""Decision artefact writer: build_decision_artefact_row (pure row construction).

Per docs/superpowers/specs/2026-07-02-phase-c-remainder-design.md, this is a
standalone writer with no automatic trigger (no /chat/answer hook) — Phase E
owns deciding when artefacts get created automatically.
"""

from __future__ import annotations

import uuid

from app.db.models import DecisionArtefact
from app.intelligence.tiers import validate_writer_tier

__all__ = ["build_decision_artefact_row"]


def build_decision_artefact_row(
    *,
    artefact_id: uuid.UUID,
    artefact_type: str,
    domain: str | None,
    question: str | None,
    answer: str | None,
    linked_thesis_ids: list[uuid.UUID],
    linked_capsule_ids: list[uuid.UUID],
    source_refs: list,
    created_by_tier: str,
) -> DecisionArtefact:
    validate_writer_tier(created_by_tier)
    return DecisionArtefact(
        id=artefact_id,
        artefact_type=artefact_type,
        domain=domain,
        question=question,
        answer=answer,
        linked_thesis_ids=linked_thesis_ids,
        linked_capsule_ids=linked_capsule_ids,
        source_refs=source_refs,
        created_by_tier=created_by_tier,
    )
