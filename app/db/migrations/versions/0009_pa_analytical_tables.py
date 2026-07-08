"""Add Perpetual Analyst analytical-memory tables.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watch_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.add_column(
        "claims",
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watch_topics.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("claims", sa.Column("source_authority", sa.Float(), nullable=True))
    op.alter_column("claims", "claim_type", nullable=True)

    op.create_table(
        "source_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watch_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=True),
        sa.Column("incentive_note", sa.Text(), nullable=True),
        sa.Column("reliability", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_source_profiles_topic_id", "source_profiles", ["topic_id"])

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watch_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("entities_json", postgresql.JSONB, nullable=True),
        sa.Column("claim_ids", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_events_topic_id", "events", ["topic_id"])

    op.create_table(
        "narrative_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watch_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column(
            "prev_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("narrative_states.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("supporting_claim_ids", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("topic_id", "version", name="uq_narrative_states_topic_version"),
    )
    op.create_index("ix_narrative_states_topic_id", "narrative_states", ["topic_id"])

    op.create_table(
        "hypotheses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watch_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("supporting_claim_ids", postgresql.JSONB, nullable=True),
        sa.Column("contradicting_claim_ids", postgresql.JSONB, nullable=True),
        sa.Column("invalidation_criteria", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_hypotheses_topic_id", "hypotheses", ["topic_id"])

    op.create_table(
        "predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watch_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "hypothesis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("hypotheses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("probability", sa.Float(), nullable=True),
        sa.Column("horizon_days", sa.Integer(), nullable=True),
        sa.Column("resolve_by", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resolution_criteria", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("outcome_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_predictions_topic_id", "predictions", ["topic_id"])

    op.create_table(
        "user_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watch_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("interests_json", postgresql.JSONB, nullable=True),
        sa.Column("framing_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_index("ix_predictions_topic_id", table_name="predictions")
    op.drop_table("predictions")
    op.drop_index("ix_hypotheses_topic_id", table_name="hypotheses")
    op.drop_table("hypotheses")
    op.drop_index("ix_narrative_states_topic_id", table_name="narrative_states")
    op.drop_table("narrative_states")
    op.drop_index("ix_events_topic_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_source_profiles_topic_id", table_name="source_profiles")
    op.drop_table("source_profiles")

    op.drop_column("claims", "source_authority")
    op.drop_column("claims", "topic_id")
    op.execute(sa.text("UPDATE claims SET claim_type = 'unknown' WHERE claim_type IS NULL"))
    op.alter_column("claims", "claim_type", nullable=False)

    op.drop_table("watch_topics")
