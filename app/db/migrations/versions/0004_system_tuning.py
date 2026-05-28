"""Add claim category, embedding, temporal validity, canonical clustering.

Combined system-tuning migration:
  S2: claims.category (hierarchical taxonomy — top-level grouping)
  S5: claims.claim_embedding (pgvector 384, mirrors span embedding model)
  S9: claims.valid_from, claims.valid_to, claims.superseded_by (temporal validity)
  S4: claims.canonical_claim_id (cross-claim cluster pointer; nullable, self-reference)

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("category", sa.Text(), nullable=True))
    op.add_column("claims", sa.Column("claim_embedding", Vector(384), nullable=True))
    op.add_column(
        "claims",
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column("canonical_claim_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_claims_superseded_by",
        "claims",
        "claims",
        ["superseded_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_claims_canonical_claim_id",
        "claims",
        "claims",
        ["canonical_claim_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_claims_category", "claims", ["category"])
    op.create_index("ix_claims_canonical_claim_id", "claims", ["canonical_claim_id"])
    op.create_index(
        "ix_claims_validity",
        "claims",
        ["valid_from", "valid_to"],
        postgresql_where=sa.text("superseded_by IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_claims_validity", table_name="claims")
    op.drop_index("ix_claims_canonical_claim_id", table_name="claims")
    op.drop_index("ix_claims_category", table_name="claims")
    op.drop_constraint("fk_claims_canonical_claim_id", "claims", type_="foreignkey")
    op.drop_constraint("fk_claims_superseded_by", "claims", type_="foreignkey")
    op.drop_column("claims", "canonical_claim_id")
    op.drop_column("claims", "superseded_by")
    op.drop_column("claims", "valid_to")
    op.drop_column("claims", "valid_from")
    op.drop_column("claims", "claim_embedding")
    op.drop_column("claims", "category")
