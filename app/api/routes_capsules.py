from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.api.deps import DbSession
from app.db.models import (
    CapsuleSegment,
    Document,
    SemanticCapsule,
    SemanticRelation,
    Span,
    Thesis,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["capsules"])

_EXCERPT_MAX = 200


def _excerpt(text: str, max_len: int = _EXCERPT_MAX) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len]


def _relation_out(rel: SemanticRelation, direction: str, other: SemanticCapsule) -> RelationOut:
    return RelationOut(
        id=rel.id,
        direction=direction,
        relation_type=rel.relation_type,
        polarity=rel.polarity,
        strength=rel.strength,
        other_capsule=OtherCapsuleOut(
            id=other.id,
            text_excerpt=_excerpt(other.text),
            lifecycle_state=other.lifecycle_state,
        ),
    )


class CapsuleOut(BaseModel):
    id: uuid.UUID
    text: str
    object_family: str
    domain_object_type: str
    core_type: str
    lifecycle_state: str
    salience: float
    confidence: float
    created_at: datetime


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str | None
    url: str | None
    published_at: datetime | None


class SpanOut(BaseModel):
    id: uuid.UUID
    span_index: int
    text_excerpt: str


class OtherCapsuleOut(BaseModel):
    id: uuid.UUID
    text_excerpt: str
    lifecycle_state: str


class RelationOut(BaseModel):
    id: uuid.UUID
    direction: str
    relation_type: str
    polarity: str | None
    strength: float
    other_capsule: OtherCapsuleOut


class ThesisOut(BaseModel):
    id: uuid.UUID
    statement_excerpt: str


class ProvenanceOut(BaseModel):
    capsule: CapsuleOut
    document: DocumentOut
    spans: list[SpanOut]
    relations: list[RelationOut]
    theses: list[ThesisOut]


@router.get("/capsules/{capsule_id}/provenance", response_model=ProvenanceOut)
async def capsule_provenance(capsule_id: uuid.UUID, db: DbSession) -> ProvenanceOut:
    capsule = await db.get(SemanticCapsule, capsule_id)
    if capsule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capsule not found.")

    document = await db.get(Document, capsule.document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capsule not found.")

    span_rows = (
        (
            await db.execute(
                select(Span)
                .join(CapsuleSegment, CapsuleSegment.segment_id == Span.id)
                .where(CapsuleSegment.capsule_id == capsule_id)
                .order_by(Span.span_index)
            )
        )
        .scalars()
        .all()
    )

    outgoing = (
        (
            await db.execute(
                select(SemanticRelation).where(
                    SemanticRelation.source_capsule_id == capsule_id,
                    SemanticRelation.target_capsule_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    incoming = (
        (
            await db.execute(
                select(SemanticRelation).where(SemanticRelation.target_capsule_id == capsule_id)
            )
        )
        .scalars()
        .all()
    )

    other_capsule_ids: set[uuid.UUID] = set()
    for rel in outgoing:
        if rel.target_capsule_id is not None:
            other_capsule_ids.add(rel.target_capsule_id)
    for rel in incoming:
        other_capsule_ids.add(rel.source_capsule_id)

    other_capsules: dict[uuid.UUID, SemanticCapsule] = {}
    if other_capsule_ids:
        other_rows = (
            (
                await db.execute(
                    select(SemanticCapsule).where(SemanticCapsule.id.in_(other_capsule_ids))
                )
            )
            .scalars()
            .all()
        )
        other_capsules = {row.id: row for row in other_rows}

    relations: list[RelationOut] = []
    for rel in outgoing:
        target_id = rel.target_capsule_id
        if target_id is None:
            continue
        other = other_capsules.get(target_id)
        if other is None:
            logger.warning("Skipping relation %s: other capsule row missing", rel.id)
            continue
        relations.append(_relation_out(rel, "out", other))

    for rel in incoming:
        other = other_capsules.get(rel.source_capsule_id)
        if other is None:
            logger.warning("Skipping relation %s: other capsule row missing", rel.id)
            continue
        relations.append(_relation_out(rel, "in", other))

    thesis_rows = (
        (
            await db.execute(
                select(Thesis).where(
                    or_(
                        Thesis.supporting_capsule_ids.contains([capsule_id]),
                        Thesis.contradicting_capsule_ids.contains([capsule_id]),
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    return ProvenanceOut(
        capsule=CapsuleOut(
            id=capsule.id,
            text=capsule.text,
            object_family=capsule.object_family,
            domain_object_type=capsule.domain_object_type,
            core_type=capsule.core_type,
            lifecycle_state=capsule.lifecycle_state,
            salience=capsule.salience,
            confidence=capsule.confidence,
            created_at=capsule.created_at,
        ),
        document=DocumentOut(
            id=document.id,
            title=document.title,
            url=document.url,
            published_at=document.published_at,
        ),
        spans=[
            SpanOut(
                id=span.id,
                span_index=span.span_index,
                text_excerpt=_excerpt(span.text),
            )
            for span in span_rows
        ],
        relations=relations,
        theses=[
            ThesisOut(id=thesis.id, statement_excerpt=_excerpt(thesis.statement))
            for thesis in thesis_rows
        ],
    )
