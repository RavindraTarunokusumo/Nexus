"""Initial schema — all 8 tables with pgvector extension

Revision ID: 0001
Revises:
Create Date: 2026-05-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=True, unique=True),
        sa.Column("domain_pack", sa.Text, nullable=False, server_default="personal_ai_tech"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("credibility_score", sa.Float, nullable=False, server_default="0.8"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_sources_source_type", "sources", ["source_type"])
    op.create_index("ix_sources_domain_pack", "sources", ["domain_pack"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=True, unique=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("clean_text", sa.Text, nullable=True),
        sa.Column("content_hash", sa.Text, nullable=False, unique=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "fetched_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="fetched"),
    )
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_fetched_at", "documents", ["fetched_at"])

    op.create_table(
        "spans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("span_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("embedding", sa.Text, nullable=True),  # placeholder; vector added below
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
    )
    # Replace TEXT placeholder with actual vector column
    op.execute("ALTER TABLE spans DROP COLUMN embedding")
    op.execute("ALTER TABLE spans ADD COLUMN embedding vector(384)")
    op.create_index("ix_spans_document_id", "spans", ["document_id"])
    op.create_index("ix_spans_span_index", "spans", ["document_id", "span_index"])

    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("claim_type", sa.Text, nullable=False),
        sa.Column("entities_json", postgresql.JSONB, nullable=True),
        sa.Column("topics_json", postgresql.JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_claims_document_id", "claims", ["document_id"])
    op.create_index("ix_claims_status", "claims", ["status"])
    op.create_index("ix_claims_claim_type", "claims", ["claim_type"])

    op.create_table(
        "claim_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "span_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_role", sa.Text, nullable=False),
        sa.Column("quote", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
    )
    op.create_index("ix_claim_evidence_claim_id", "claim_evidence", ["claim_id"])
    op.create_index("ix_claim_evidence_span_id", "claim_evidence", ["span_id"])

    op.create_table(
        "briefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brief_type", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("domain_pack", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_briefs_brief_type", "briefs", ["brief_type"])
    op.create_index("ix_briefs_domain_pack", "briefs", ["domain_pack"])
    op.create_index("ix_briefs_created_at", "briefs", ["created_at"])

    op.create_table(
        "brief_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brief_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("briefs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("why_it_matters", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("claim_ids", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_brief_items_brief_id", "brief_items", ["brief_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_type", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=True),
        sa.Column("input_json", postgresql.JSONB, nullable=True),
        sa.Column("output_json", postgresql.JSONB, nullable=True),
        sa.Column("cost_estimate", sa.Float, nullable=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_agent_runs_run_type", "agent_runs", ["run_type"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_table("brief_items")
    op.drop_table("briefs")
    op.drop_table("claim_evidence")
    op.drop_table("claims")
    op.drop_table("spans")
    op.drop_table("documents")
    op.drop_table("sources")
    op.execute("DROP EXTENSION IF EXISTS vector")
