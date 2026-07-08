"""Add GIN index on spans.metadata_json entities for entity-anchored retrieval.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-07
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_spans_metadata_entities_gin
        ON spans USING gin ((metadata_json -> 'entities'))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_spans_metadata_entities_gin")
