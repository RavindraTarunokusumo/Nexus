import os
import subprocess
import sys

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.api.routes_ingestion import router as ingestion_router
from app.api.routes_sources import router as sources_router
from app.db.models import Base


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer(image="pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture(scope="session")
def db_url(pg_container):
    host = pg_container.get_container_host_ip()
    port = pg_container.get_exposed_port(5432)
    return (
        f"postgresql+asyncpg://{pg_container.username}:{pg_container.password}"
        f"@{host}:{port}/{pg_container.dbname}"
    )


@pytest.fixture(scope="session", autouse=True)
def run_migrations(db_url):
    """Run Alembic migrations in a subprocess to avoid event-loop conflicts."""
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


@pytest_asyncio.fixture(scope="session")
async def async_engine(db_url):
    engine = create_async_engine(db_url, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_factory(async_engine):
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def clean_db(async_engine):
    """Delete all rows (children first) before each test."""
    async with async_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def client(async_engine, session_factory):
    """FastAPI test client wired to the test database (no lifespan side-effects)."""
    test_app = FastAPI()
    test_app.state.engine = async_engine
    test_app.state.session_factory = session_factory
    test_app.include_router(sources_router)
    test_app.include_router(ingestion_router)

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as c:
        yield c
