"""Migration 0005 — semantic capsule layer.

Asserts every table / index / CHECK / FK declared in
docs/superpowers/plans/2026-06-02-phase-b-capsule-schema.md §4 is present
after `alembic upgrade head`, and that the downgrade tears them all down.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

_REPO_ROOT = Path(__file__).resolve().parents[2]

CAPSULE_TABLES = (
    "domain_packs",
    "semantic_capsules",
    "capsule_segments",
    "theses",
    "semantic_relations",
    "decision_artefacts",
)

EXPECTED_INDEXES = {
    "ix_semantic_capsules_source_id",
    "ix_semantic_capsules_document_id",
    "ix_semantic_capsules_claim_id",
    "ix_capsule_segments_segment_id",
    "ix_theses_domain",
    "ix_semantic_relations_source",
    "ix_semantic_relations_target_capsule",
    "ix_semantic_relations_target_thesis",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _table_exists(engine: AsyncEngine, name: str) -> bool:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT to_regclass(:n)").bindparams(n=f"public.{name}"))
        return result.scalar_one() is not None


async def _column_type(engine: AsyncEngine, table: str, column: str) -> str | None:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ).bindparams(t=table, c=column)
        )
        row = result.first()
        return row[0] if row else None


async def _insert_source_document_span(engine: AsyncEngine) -> tuple[uuid.UUID, ...]:
    """Insert one source + document + span and return their ids."""
    source_id = uuid.uuid4()
    document_id = uuid.uuid4()
    span_id = uuid.uuid4()
    content_hash = hashlib.sha256(str(document_id).encode()).hexdigest()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sources (id, name, source_type, domain_pack, enabled, "
                "credibility_score) VALUES (:id,'src','rss','personal_ai_tech',true,0.8)"
            ).bindparams(id=source_id)
        )
        await conn.execute(
            text(
                "INSERT INTO documents (id, source_id, content_hash, status) "
                "VALUES (:id,:src,:h,'fetched')"
            ).bindparams(id=document_id, src=source_id, h=content_hash)
        )
        await conn.execute(
            text(
                "INSERT INTO spans (id, document_id, span_index, text) "
                "VALUES (:id,:doc,0,'span text')"
            ).bindparams(id=span_id, doc=document_id)
        )
    return source_id, document_id, span_id


async def _cleanup_capsule_rows(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM capsule_segments"))
        await conn.execute(text("DELETE FROM semantic_capsules"))
        await conn.execute(text("DELETE FROM spans"))
        await conn.execute(text("DELETE FROM documents"))
        await conn.execute(text("DELETE FROM sources WHERE name='src'"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(async_engine: AsyncEngine):
    """Each test starts with the capsule tables truncated."""
    await _cleanup_capsule_rows(async_engine)
    yield
    await _cleanup_capsule_rows(async_engine)


class TestTablesExist:
    @pytest.mark.parametrize("table", CAPSULE_TABLES)
    @pytest.mark.asyncio
    async def test_table_present(self, async_engine: AsyncEngine, table: str) -> None:
        assert await _table_exists(async_engine, table), f"{table} missing"

    @pytest.mark.asyncio
    async def test_embedding_is_vector_type(self, async_engine: AsyncEngine) -> None:
        udt = await _column_type(async_engine, "semantic_capsules", "embedding")
        assert udt == "vector", f"expected pgvector 'vector' type, got {udt!r}"


class TestIndexes:
    @pytest.mark.asyncio
    async def test_expected_indexes_present(self, async_engine: AsyncEngine) -> None:
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname='public' AND tablename = ANY(:tables)"
                ).bindparams(tables=list(CAPSULE_TABLES))
            )
            present = {row[0] for row in result}
        missing = EXPECTED_INDEXES - present
        assert not missing, f"missing indexes: {missing}"


class TestCheckConstraints:
    @pytest.mark.asyncio
    async def test_invalid_core_type_rejected(self, async_engine: AsyncEngine) -> None:
        source_id, document_id, _ = await _insert_source_document_span(async_engine)
        with pytest.raises(IntegrityError):
            async with async_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO semantic_capsules "
                        "(source_id, document_id, idempotency_key, core_type, text, "
                        " domain, object_family, domain_object_type, created_by_tier) "
                        "VALUES (:s,:d,'k1','banana','t','personal_ai_tech',"
                        " 'fact','assertion','t2')"
                    ).bindparams(s=source_id, d=document_id)
                )

    @pytest.mark.asyncio
    async def test_invalid_lifecycle_state_rejected(self, async_engine: AsyncEngine) -> None:
        source_id, document_id, _ = await _insert_source_document_span(async_engine)
        with pytest.raises(IntegrityError):
            async with async_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO semantic_capsules "
                        "(source_id, document_id, idempotency_key, core_type, text, "
                        " domain, object_family, domain_object_type, created_by_tier, "
                        " lifecycle_state) "
                        "VALUES (:s,:d,'k2','claim','t','personal_ai_tech',"
                        " 'fact','assertion','t2','banana')"
                    ).bindparams(s=source_id, d=document_id)
                )

    @pytest.mark.asyncio
    async def test_invalid_escalation_state_rejected(self, async_engine: AsyncEngine) -> None:
        source_id, document_id, _ = await _insert_source_document_span(async_engine)
        with pytest.raises(IntegrityError):
            async with async_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO semantic_capsules "
                        "(source_id, document_id, idempotency_key, core_type, text, "
                        " domain, object_family, domain_object_type, created_by_tier, "
                        " escalation_state) "
                        "VALUES (:s,:d,'k3','claim','t','personal_ai_tech',"
                        " 'fact','assertion','t2','exploded')"
                    ).bindparams(s=source_id, d=document_id)
                )

    @pytest.mark.asyncio
    async def test_relations_xor_constraint(self, async_engine: AsyncEngine) -> None:
        source_id, document_id, _ = await _insert_source_document_span(async_engine)
        # First create a real capsule so we can reference it as source.
        capsule_id = uuid.uuid4()
        async with async_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO semantic_capsules "
                    "(id, source_id, document_id, idempotency_key, core_type, text, "
                    " domain, object_family, domain_object_type, created_by_tier) "
                    "VALUES (:id,:s,:d,'k-rel','claim','t','personal_ai_tech',"
                    " 'fact','assertion','t2')"
                ).bindparams(id=capsule_id, s=source_id, d=document_id)
            )
        # Now: relation with neither target_capsule_id nor target_thesis_id violates XOR.
        with pytest.raises(IntegrityError):
            async with async_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO semantic_relations "
                        "(source_capsule_id, relation_type, created_by_tier) "
                        "VALUES (:src,'supports','t2')"
                    ).bindparams(src=capsule_id)
                )


class TestUniqueAndForeignKeys:
    @pytest.mark.asyncio
    async def test_idempotency_key_unique(self, async_engine: AsyncEngine) -> None:
        source_id, document_id, _ = await _insert_source_document_span(async_engine)
        async with async_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO semantic_capsules "
                    "(source_id, document_id, idempotency_key, core_type, text, "
                    " domain, object_family, domain_object_type, created_by_tier) "
                    "VALUES (:s,:d,'dup-key','claim','t','personal_ai_tech',"
                    " 'fact','assertion','t2')"
                ).bindparams(s=source_id, d=document_id)
            )
        with pytest.raises(IntegrityError):
            async with async_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO semantic_capsules "
                        "(source_id, document_id, idempotency_key, core_type, text, "
                        " domain, object_family, domain_object_type, created_by_tier) "
                        "VALUES (:s,:d,'dup-key','claim','t2','personal_ai_tech',"
                        " 'fact','assertion','t2')"
                    ).bindparams(s=source_id, d=document_id)
                )

    @pytest.mark.asyncio
    async def test_source_delete_cascades_capsule(self, async_engine: AsyncEngine) -> None:
        source_id, document_id, _ = await _insert_source_document_span(async_engine)
        async with async_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO semantic_capsules "
                    "(source_id, document_id, idempotency_key, core_type, text, "
                    " domain, object_family, domain_object_type, created_by_tier) "
                    "VALUES (:s,:d,'k-fk','claim','t','personal_ai_tech',"
                    " 'fact','assertion','t2')"
                ).bindparams(s=source_id, d=document_id)
            )
        async with async_engine.begin() as conn:
            # Sources have FK from documents; cascade-delete the source.
            await conn.execute(text("DELETE FROM sources WHERE id = :s").bindparams(s=source_id))
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT count(*) FROM semantic_capsules WHERE source_id = :s").bindparams(
                    s=source_id
                )
            )
            assert result.scalar_one() == 0

    @pytest.mark.asyncio
    async def test_capsule_delete_cascades_segments(self, async_engine: AsyncEngine) -> None:
        source_id, document_id, span_id = await _insert_source_document_span(async_engine)
        capsule_id = uuid.uuid4()
        async with async_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO semantic_capsules "
                    "(id, source_id, document_id, idempotency_key, core_type, text, "
                    " domain, object_family, domain_object_type, created_by_tier) "
                    "VALUES (:id,:s,:d,'k-seg','claim','t','personal_ai_tech',"
                    " 'fact','assertion','t2')"
                ).bindparams(id=capsule_id, s=source_id, d=document_id)
            )
            await conn.execute(
                text(
                    "INSERT INTO capsule_segments (capsule_id, segment_id, role) "
                    "VALUES (:c,:seg,'grounds')"
                ).bindparams(c=capsule_id, seg=span_id)
            )
        async with async_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM semantic_capsules WHERE id = :id").bindparams(id=capsule_id)
            )
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT count(*) FROM capsule_segments WHERE capsule_id = :c").bindparams(
                    c=capsule_id
                )
            )
            assert result.scalar_one() == 0

    @pytest.mark.asyncio
    async def test_claim_delete_sets_capsule_claim_id_null(self, async_engine: AsyncEngine) -> None:
        source_id, document_id, _ = await _insert_source_document_span(async_engine)
        claim_id = uuid.uuid4()
        capsule_id = uuid.uuid4()
        async with async_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO claims (id, document_id, claim_text, claim_type, "
                    "status) VALUES (:id,:d,'text','assertion','active')"
                ).bindparams(id=claim_id, d=document_id)
            )
            await conn.execute(
                text(
                    "INSERT INTO semantic_capsules "
                    "(id, source_id, document_id, claim_id, idempotency_key, "
                    " core_type, text, domain, object_family, domain_object_type, "
                    " created_by_tier) "
                    "VALUES (:id,:s,:d,:cl,'k-claim','claim','t','personal_ai_tech',"
                    " 'fact','assertion','t2')"
                ).bindparams(id=capsule_id, s=source_id, d=document_id, cl=claim_id)
            )
        async with async_engine.begin() as conn:
            await conn.execute(text("DELETE FROM claims WHERE id = :id").bindparams(id=claim_id))
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT claim_id FROM semantic_capsules WHERE id = :id").bindparams(
                    id=capsule_id
                )
            )
            assert result.scalar_one() is None


def _run_alembic(cmd: list[str], db_url: str) -> subprocess.CompletedProcess[str]:
    """Run an alembic command in a child process (sync — invoked off the loop)."""
    env = {**os.environ, "DATABASE_URL": db_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *cmd],
        env=env,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )


class TestDowngrade:
    """downgrade(0004) → re-upgrade(head); each step verified via to_regclass.

    The subprocess.run calls are wrapped via asyncio.to_thread so the async test
    body never blocks the event loop (ruff ASYNC221).
    """

    @pytest.mark.asyncio
    async def test_round_trip(self, async_engine: AsyncEngine, db_url: str) -> None:
        import asyncio

        down = await asyncio.to_thread(_run_alembic, ["downgrade", "0004"], db_url)
        assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"
        for table in CAPSULE_TABLES:
            assert not await _table_exists(
                async_engine, table
            ), f"{table} should be gone after downgrade"

        up = await asyncio.to_thread(_run_alembic, ["upgrade", "head"], db_url)
        assert up.returncode == 0, f"re-upgrade failed:\n{up.stdout}\n{up.stderr}"
        for table in CAPSULE_TABLES:
            assert await _table_exists(
                async_engine, table
            ), f"{table} should be back after re-upgrade"
