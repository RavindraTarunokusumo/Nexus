"""Add eval_datasets, eval_runs, eval_results tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eval_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("example_count", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "task", "version", name="uq_eval_datasets_name_task_version"),
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sut_model", sa.Text(), nullable=False),
        sa.Column("sut_prompt_version", sa.Text(), nullable=False),
        sa.Column("judge_name", sa.Text(), nullable=False),
        sa.Column("judge_model", sa.Text(), nullable=False),
        sa.Column("judge_prompt_version", sa.Text(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("aggregate_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("example_id", sa.Text(), nullable=False),
        sa.Column("sut_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("judge_verdict", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "deterministic_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["eval_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eval_runs_dataset_id", "eval_runs", ["dataset_id"])
    op.create_index("ix_eval_results_run_id", "eval_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_results_run_id", table_name="eval_results")
    op.drop_index("ix_eval_runs_dataset_id", table_name="eval_runs")
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
    op.drop_table("eval_datasets")
