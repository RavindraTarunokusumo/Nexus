"""Add HNSW index on semantic_capsules.embedding for ANN retrieval.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_semantic_capsules_embedding_hnsw
        ON semantic_capsules
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_semantic_capsules_embedding_hnsw")
