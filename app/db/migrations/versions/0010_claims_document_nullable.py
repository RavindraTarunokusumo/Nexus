"""Make claims.document_id nullable — PA synthesized claims are topic-level.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("claims", "document_id", nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM claims WHERE document_id IS NULL")
    op.alter_column("claims", "document_id", nullable=False)
