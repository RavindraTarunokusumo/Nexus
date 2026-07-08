"""Add nullable scope column to documents for corpus/topic scoping.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("scope", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "scope")
