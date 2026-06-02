"""Self-contained Postgres fixtures for the schema-only Phase B migration tests.

The parent tests/conftest.py imports app.api.routes_chat, which transitively
requires langgraph.checkpoint.postgres — a package not always installed in the
local dev venv. These migration tests only need a Postgres engine + Alembic;
they have no API/LangGraph surface to exercise. Keeping a dedicated conftest
under tests/db/ lets pytest collect this module without dragging in the parent
chain.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

_REPO_ROOT = Path(__file__).resolve().parents[2]
# Local dev fixture only — CI uses the Postgres testcontainer path above.
_LOCAL_DB_URL = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    """An asyncpg URL pointing at a Postgres with pgvector preinstalled."""
    if _docker_available():
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer(image="pgvector/pgvector:pg16") as container:
            host = container.get_container_host_ip()
            port = container.get_exposed_port(5432)
            yield (
                f"postgresql+asyncpg://{container.username}:{container.password}"
                f"@{host}:{port}/{container.dbname}"
            )
    else:
        yield _LOCAL_DB_URL


@pytest.fixture(scope="session")
def alembic_upgrade(db_url: str) -> str:
    """Run `alembic upgrade head` once per session via subprocess."""
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert (
        result.returncode == 0
    ), f"Alembic upgrade failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return db_url


@pytest_asyncio.fixture
async def async_engine(alembic_upgrade: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(alembic_upgrade, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(async_engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(async_engine, expire_on_commit=False)
