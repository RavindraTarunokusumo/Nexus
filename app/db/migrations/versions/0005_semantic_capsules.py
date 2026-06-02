"""Add semantic capsule layer (v0.7) — six tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-02

Schema only — no application reader/writer yet. B2 wires dual-write.

Per docs/superpowers/plans/2026-06-02-phase-b-capsule-schema.md §4:
- domain_packs        (registry; YAML stays source of truth)
- semantic_capsules   (typed capsule rows; VECTOR(384) embedding;
                       CHECK on core_type / lifecycle_state /
                       escalation_state; idempotency_key UNIQUE)
- capsule_segments    (capsule × span join; sole source of truth
                       for capsule provenance)
- semantic_relations  (capsule × capsule edges; XOR target capsule
                       or thesis)
- theses              (higher-order interpretation; UUID arrays of
                       supporting / contradicting capsule ids)
- decision_artefacts  (memo/alert/trade-idea outputs)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


# CHECK vocabularies — plan §4.
_CORE_TYPES = (
    "claim",
    "event",
    "observation",
    "result",
    "risk",
    "argument",
    "explanation",
    "comparison",
    "definition",
    "constraint",
    "question",
    "description",
    "state_change",
    "narrative_development",
    "other",
)
_LIFECYCLE_STATES = (
    "candidate",
    "active",
    "confirmed",
    "qualified",
    "contradicted",
    "superseded",
    "stale",
    "archived",
    "rejected",
)
_ESCALATION_STATES = ("none", "flagged", "escalated", "resolved")
_CAPSULE_TIERS = ("t0", "t1", "t2", "t3", "t4", "backfill")
_RELATION_TIERS = ("t1", "t2", "t3", "t4")
_THESIS_TIERS = ("t2", "t3", "t4")
_DECISION_TIERS = ("t2", "t3", "t4")
_RELATION_TYPES = (
    "supports",
    "contradicts",
    "refines",
    "exemplifies",
    "qualifies",
    "supersedes",
    "depends_on",
    "other",
)
_SEGMENT_ROLES = (
    "grounds",
    "supports",
    "contradicts",
    "qualifies",
    "refines",
    "exemplifies",
    "other",
)


def _in_check(col: str, values: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{col} IN ({quoted})"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. domain_packs — registry only; YAML stays source of truth.
    # ------------------------------------------------------------------
    op.create_table(
        "domain_packs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column(
            "source_types",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "parent_pack_id",
            sa.Text(),
            sa.ForeignKey("domain_packs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pack_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # 2. semantic_capsules — typed capsule rows.
    # ------------------------------------------------------------------
    op.create_table(
        "semantic_capsules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("core_type", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("source_telos", sa.Text(), nullable=True),
        sa.Column("object_family", sa.Text(), nullable=False),
        sa.Column("domain_object_type", sa.Text(), nullable=False),
        sa.Column("function", sa.Text(), nullable=True),
        sa.Column(
            "facets",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "epistemic_state",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "salience",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
        sa.Column(
            "lifecycle_state",
            sa.Text(),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "escalation_state",
            sa.Text(),
            nullable=False,
            server_default="none",
        ),
        # embedding VECTOR(384) added via raw DDL below — matches the pattern
        # used in 0001 for spans.embedding (pgvector type is not a vanilla
        # SQLAlchemy column at the Alembic layer).
        sa.Column("created_by_tier", sa.Text(), nullable=False),
        sa.Column("created_by_model", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _in_check("core_type", _CORE_TYPES),
            name="ck_semantic_capsules_core_type",
        ),
        sa.CheckConstraint(
            _in_check("lifecycle_state", _LIFECYCLE_STATES),
            name="ck_semantic_capsules_lifecycle_state",
        ),
        sa.CheckConstraint(
            _in_check("escalation_state", _ESCALATION_STATES),
            name="ck_semantic_capsules_escalation_state",
        ),
        sa.CheckConstraint(
            _in_check("created_by_tier", _CAPSULE_TIERS),
            name="ck_semantic_capsules_created_by_tier",
        ),
        sa.CheckConstraint(
            "salience BETWEEN 0 AND 1",
            name="ck_semantic_capsules_salience_range",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_semantic_capsules_confidence_range",
        ),
    )
    # pgvector VECTOR(384) — same pattern as 0001 spans.embedding.
    op.execute("ALTER TABLE semantic_capsules ADD COLUMN embedding vector(384)")

    op.create_index(
        "ix_semantic_capsules_source_id",
        "semantic_capsules",
        ["source_id"],
    )
    op.create_index(
        "ix_semantic_capsules_document_id",
        "semantic_capsules",
        ["document_id"],
    )
    op.create_index(
        "ix_semantic_capsules_claim_id",
        "semantic_capsules",
        ["claim_id"],
        postgresql_where=sa.text("claim_id IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # 3. capsule_segments — capsule × span join.
    # ------------------------------------------------------------------
    op.create_table(
        "capsule_segments",
        sa.Column(
            "capsule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("semantic_capsules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "segment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
            server_default="grounds",
        ),
        sa.PrimaryKeyConstraint("capsule_id", "segment_id"),
        sa.CheckConstraint(
            _in_check("role", _SEGMENT_ROLES),
            name="ck_capsule_segments_role",
        ),
    )
    op.create_index(
        "ix_capsule_segments_segment_id",
        "capsule_segments",
        ["segment_id"],
    )

    # ------------------------------------------------------------------
    # 4. theses — higher-order interpretation; written first by Phase E.
    # ------------------------------------------------------------------
    op.create_table(
        "theses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("thesis_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
        sa.Column(
            "scope",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "invalidation_criteria",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "supporting_capsule_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "contradicting_capsule_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "epistemic_state",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "lifecycle_state",
            sa.Text(),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_by_tier", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _in_check("lifecycle_state", _LIFECYCLE_STATES),
            name="ck_theses_lifecycle_state",
        ),
        sa.CheckConstraint(
            _in_check("created_by_tier", _THESIS_TIERS),
            name="ck_theses_created_by_tier",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_theses_confidence_range",
        ),
    )
    op.create_index("ix_theses_domain", "theses", ["domain"])

    # ------------------------------------------------------------------
    # 5. semantic_relations — capsule × capsule / thesis edges.
    #    Created AFTER theses so the target_thesis_id FK resolves.
    # ------------------------------------------------------------------
    op.create_table(
        "semantic_relations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_capsule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("semantic_capsules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_capsule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("semantic_capsules.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "target_thesis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("theses.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("domain_relation_type", sa.Text(), nullable=True),
        sa.Column("polarity", sa.Text(), nullable=True),
        sa.Column(
            "strength",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
        sa.Column(
            "evidence_capsule_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "epistemic_state",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by_tier", sa.Text(), nullable=False),
        sa.Column("created_by_model", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _in_check("relation_type", _RELATION_TYPES),
            name="ck_semantic_relations_relation_type",
        ),
        sa.CheckConstraint(
            "polarity IS NULL OR polarity IN ('positive','negative','neutral')",
            name="ck_semantic_relations_polarity",
        ),
        sa.CheckConstraint(
            _in_check("created_by_tier", _RELATION_TIERS),
            name="ck_semantic_relations_created_by_tier",
        ),
        sa.CheckConstraint(
            "strength BETWEEN 0 AND 1",
            name="ck_semantic_relations_strength_range",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_semantic_relations_confidence_range",
        ),
        sa.CheckConstraint(
            "target_capsule_id IS NOT NULL OR target_thesis_id IS NOT NULL",
            name="ck_semantic_relations_target_xor",
        ),
    )
    op.create_index(
        "ix_semantic_relations_source",
        "semantic_relations",
        ["source_capsule_id"],
    )
    op.create_index(
        "ix_semantic_relations_target_capsule",
        "semantic_relations",
        ["target_capsule_id"],
        postgresql_where=sa.text("target_capsule_id IS NOT NULL"),
    )
    op.create_index(
        "ix_semantic_relations_target_thesis",
        "semantic_relations",
        ["target_thesis_id"],
        postgresql_where=sa.text("target_thesis_id IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # 6. decision_artefacts — memo / alert / trade-idea outputs.
    # ------------------------------------------------------------------
    op.create_table(
        "decision_artefacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("artefact_type", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column(
            "linked_thesis_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "linked_capsule_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "source_refs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "epistemic_state",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by_tier", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _in_check("created_by_tier", _DECISION_TIERS),
            name="ck_decision_artefacts_created_by_tier",
        ),
    )


def downgrade() -> None:
    # Reverse FK order: dependants first.
    op.drop_table("decision_artefacts")

    op.drop_index(
        "ix_semantic_relations_target_thesis",
        table_name="semantic_relations",
    )
    op.drop_index(
        "ix_semantic_relations_target_capsule",
        table_name="semantic_relations",
    )
    op.drop_index("ix_semantic_relations_source", table_name="semantic_relations")
    op.drop_table("semantic_relations")

    op.drop_index("ix_theses_domain", table_name="theses")
    op.drop_table("theses")

    op.drop_index("ix_capsule_segments_segment_id", table_name="capsule_segments")
    op.drop_table("capsule_segments")

    op.drop_index("ix_semantic_capsules_claim_id", table_name="semantic_capsules")
    op.drop_index("ix_semantic_capsules_document_id", table_name="semantic_capsules")
    op.drop_index("ix_semantic_capsules_source_id", table_name="semantic_capsules")
    op.drop_table("semantic_capsules")

    op.drop_table("domain_packs")
