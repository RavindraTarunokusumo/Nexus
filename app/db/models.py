import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    domain_pack: Mapped[str] = mapped_column(Text, nullable=False, default="personal_ai_tech")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    credibility_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )

    documents: Mapped[list["Document"]] = relationship("Document", back_populates="source")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    clean_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="fetched")
    chunked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    embedded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    extraction_started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    extraction_completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    source: Mapped["Source"] = relationship("Source", back_populates="documents")
    spans: Mapped[list["Span"]] = relationship("Span", back_populates="document")
    claims: Mapped[list["Claim"]] = relationship("Claim", back_populates="document")
    capsules: Mapped[list["SemanticCapsule"]] = relationship(
        "SemanticCapsule", back_populates="document"
    )


class Span(Base):
    __tablename__ = "spans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    span_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 384 dims: BAAI/bge-small-en-v1.5 and all-MiniLM-L6-v2 both use 384
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="spans")
    evidence_links: Mapped[list["ClaimEvidence"]] = relationship(
        "ClaimEvidence", back_populates="span"
    )
    capsule_segments: Mapped[list["CapsuleSegment"]] = relationship(
        "CapsuleSegment", back_populates="span"
    )


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(Text, nullable=False)
    entities_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    topics_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )

    document: Mapped["Document"] = relationship("Document", back_populates="claims")
    evidence_links: Mapped[list["ClaimEvidence"]] = relationship(
        "ClaimEvidence", back_populates="claim"
    )


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    span_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spans.id", ondelete="CASCADE"), nullable=False
    )
    evidence_role: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    claim: Mapped["Claim"] = relationship("Claim", back_populates="evidence_links")
    span: Mapped["Span"] = relationship("Span", back_populates="evidence_links")


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brief_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain_pack: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )

    items: Mapped[list["BriefItem"]] = relationship("BriefItem", back_populates="brief")


class BriefItem(Base):
    __tablename__ = "brief_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("briefs.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_it_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    claim_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    brief: Mapped["Brief"] = relationship("Brief", back_populates="items")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_type: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    span_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )


class SpanExtraction(Base):
    __tablename__ = "span_extractions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    span_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spans.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    citations_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    retrieved_context_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")


class EvalDataset(Base):
    __tablename__ = "eval_datasets"
    __table_args__ = (
        UniqueConstraint("name", "task", "version", name="uq_eval_datasets_name_task_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    example_count: Mapped[int] = mapped_column(Integer, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )

    eval_runs: Mapped[list["EvalRun"]] = relationship("EvalRun", back_populates="dataset")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_datasets.id", ondelete="RESTRICT"), nullable=False
    )
    sut_model: Mapped[str] = mapped_column(Text, nullable=False)
    sut_prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    judge_name: Mapped[str] = mapped_column(Text, nullable=False)
    judge_model: Mapped[str] = mapped_column(Text, nullable=False)
    judge_prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    aggregate_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total_cost_usd: Mapped[float] = mapped_column(
        Numeric(precision=12, scale=6), nullable=False, default=0.0
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )

    dataset: Mapped["EvalDataset"] = relationship("EvalDataset", back_populates="eval_runs")
    results: Mapped[list["EvalResult"]] = relationship(
        "EvalResult", back_populates="run", cascade="all, delete-orphan"
    )


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    example_id: Mapped[str] = mapped_column(Text, nullable=False)
    sut_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    judge_verdict: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    deterministic_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )

    run: Mapped["EvalRun"] = relationship("EvalRun", back_populates="results")


# ---------------------------------------------------------------------------
# Phase B — Semantic capsule layer (migration 0005).
# Schema-only in B1; B2 wires dual-write from projection.
# ---------------------------------------------------------------------------


class DomainPackRegistry(Base):
    __tablename__ = "domain_packs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    source_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    parent_pack_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("domain_packs.id", ondelete="SET NULL"), nullable=True
    )
    pack_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class SemanticCapsule(Base):
    __tablename__ = "semantic_capsules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    core_type: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    source_telos: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_family: Mapped[str] = mapped_column(Text, nullable=False)
    domain_object_type: Mapped[str] = mapped_column(Text, nullable=False)
    function: Mapped[str | None] = mapped_column(Text, nullable=True)
    facets: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    epistemic_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    salience: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    lifecycle_state: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    escalation_state: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    # 384 dims, same vector space as Span.embedding.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    created_by_tier: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    document: Mapped["Document"] = relationship("Document", back_populates="capsules")


class CapsuleSegment(Base):
    __tablename__ = "capsule_segments"

    capsule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("semantic_capsules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spans.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, default="grounds")

    span: Mapped["Span"] = relationship("Span", back_populates="capsule_segments")


class Thesis(Base):
    __tablename__ = "theses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    thesis_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    invalidation_criteria: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    supporting_capsule_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    contradicting_capsule_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    epistemic_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    lifecycle_state: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_by_tier: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class SemanticRelation(Base):
    __tablename__ = "semantic_relations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_capsule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("semantic_capsules.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_capsule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("semantic_capsules.id", ondelete="CASCADE"),
        nullable=True,
    )
    target_thesis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("theses.id", ondelete="CASCADE"),
        nullable=True,
    )
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    domain_relation_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    polarity: Mapped[str | None] = mapped_column(Text, nullable=True)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    evidence_capsule_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    epistemic_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by_tier: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )


class DecisionArtefact(Base):
    __tablename__ = "decision_artefacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artefact_type: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_thesis_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    linked_capsule_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    epistemic_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by_tier: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )
