import hashlib
import os
import subprocess
import sys

import numpy as np
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes_capsules import router as capsules_router
from app.api.routes_chat import router as chat_router
from app.api.routes_chat_sessions import router as chat_sessions_router
from app.api.routes_claims import router as claims_router
from app.api.routes_documents import router as documents_router
from app.api.routes_ingestion import router as ingestion_router
from app.api.routes_sources import router as sources_router
from app.api.routes_stats import router as stats_router
from app.db.models import Base

# ---------------------------------------------------------------------------
# Mock embedder (no real model required)
# ---------------------------------------------------------------------------

_EMBED_DIM = 384


class MockEmbedder:
    """Deterministic unit-norm mock embedder for tests."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
            rng = np.random.default_rng(seed)
            vec = rng.standard_normal(_EMBED_DIM).astype(np.float64)
            vec = vec / np.linalg.norm(vec)
            result.append(vec.tolist())
        return result

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


# ---------------------------------------------------------------------------
# Database URL — testcontainers if Docker is available, else local Postgres
# ---------------------------------------------------------------------------

_LOCAL_DB_URL = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_url():
    """Return an asyncpg DB URL; uses local Postgres when Docker is unavailable."""
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
        # Local Postgres (started in CI or dev env)
        yield _LOCAL_DB_URL


@pytest.fixture(scope="session", autouse=True)
def run_migrations(db_url):
    """Run Alembic migrations once per session via subprocess (avoids event-loop conflicts)."""
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert result.returncode == 0, (
        f"Alembic migration failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Per-test engine / session
# ---------------------------------------------------------------------------


# Function-scoped engine: each test gets a fresh asyncpg pool in its own event loop.
# This avoids "Future attached to a different loop" errors from session-scoped pools.
@pytest_asyncio.fixture
async def async_engine(db_url):
    engine = create_async_engine(db_url, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(async_engine):
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def clean_db(async_engine):
    """Truncate all tables (children first) before each test."""
    async with async_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


# ---------------------------------------------------------------------------
# HTTP clients
# ---------------------------------------------------------------------------


def _build_app(async_engine, session_factory, embedder=None, memory_graph=None) -> FastAPI:
    test_app = FastAPI()
    test_app.state.engine = async_engine
    test_app.state.session_factory = session_factory
    test_app.state.embedder = embedder
    test_app.state.memory_graph = memory_graph
    test_app.include_router(sources_router)
    test_app.include_router(ingestion_router)
    test_app.include_router(documents_router)
    test_app.include_router(claims_router)
    test_app.include_router(stats_router)
    test_app.include_router(capsules_router)
    test_app.include_router(chat_router)
    test_app.include_router(chat_sessions_router)
    return test_app


@pytest_asyncio.fixture
async def client(async_engine, session_factory):
    """Test client without an embedder (search disabled, background tasks no-op embed)."""
    test_app = _build_app(async_engine, session_factory, embedder=None)
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def client_with_embedder(async_engine, session_factory):
    """Test client wired with MockEmbedder for search and chunk-embed tests."""
    test_app = _build_app(async_engine, session_factory, embedder=MockEmbedder())
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        yield c


@pytest.fixture
def mock_embedder():
    return MockEmbedder()
