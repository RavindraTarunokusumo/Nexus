"""Add observability columns: agent_runs correlation, span_extractions, documents timestamps."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from typing import Sequence, Union

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # agent_runs: correlation columns + token split
    op.add_column("agent_runs", sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("span_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("prompt_tokens", sa.Integer, nullable=True))
    op.add_column("agent_runs", sa.Column("completion_tokens", sa.Integer, nullable=True))
    op.create_index("ix_agent_runs_run_id", "agent_runs", ["run_id"])

    # documents: per-stage timestamps
    op.add_column("documents", sa.Column("chunked_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("embedded_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("extraction_started_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("extraction_completed_at", sa.TIMESTAMP(timezone=True), nullable=True))

    # span_extractions: new table
    op.create_table(
        "span_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("span_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_span_extractions_run_id", "span_extractions", ["run_id"])
    op.create_index("ix_span_extractions_document_span", "span_extractions", ["document_id", "span_id"])
    op.create_index("ix_span_extractions_status", "span_extractions", ["status"])


def downgrade() -> None:
    op.drop_table("span_extractions")
    op.drop_index("ix_agent_runs_run_id", table_name="agent_runs")
    op.drop_column("agent_runs", "run_id")
    op.drop_column("agent_runs", "document_id")
    op.drop_column("agent_runs", "span_id")
    op.drop_column("agent_runs", "prompt_tokens")
    op.drop_column("agent_runs", "completion_tokens")
    op.drop_column("documents", "chunked_at")
    op.drop_column("documents", "embedded_at")
    op.drop_column("documents", "extraction_started_at")
    op.drop_column("documents", "extraction_completed_at")
