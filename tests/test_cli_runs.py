"""Integration tests for nexus runs list / nexus runs show."""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from typer.testing import CliRunner

from app.cli.main import app
from app.db.models import AgentRun, Document, Source, Span, SpanExtraction


@pytest.fixture
def runner():
    return CliRunner()


@pytest_asyncio.fixture
async def seeded_run(session_factory):
    """Seed one agent_run + one span_extraction row sharing a run_id."""
    run_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    span_id = uuid.uuid4()
    async with session_factory() as session:
        source = Source(name="s", source_type="manual", domain_pack="personal_ai_tech")
        session.add(source)
        await session.flush()
        doc = Document(
            id=doc_id, source_id=source.id,
            clean_text="hi", raw_text="hi",
            content_hash=f"h-{uuid.uuid4()}", status="claims_extracted",
        )
        session.add(doc)
        await session.flush()
        span = Span(
            id=span_id, document_id=doc_id,
            span_index=0, text="hi",
        )
        session.add(span)
        await session.flush()
        ar = AgentRun(
            run_type="claim_extraction", model="test-m",
            input_json={"system": "sys", "user": "usr"},
            output_json={"raw": "{}"},
            cost_estimate=0.001, status="success",
            run_id=run_id, document_id=doc_id,
        )
        session.add(ar)
        se = SpanExtraction(
            run_id=run_id, span_id=span_id, document_id=doc_id,
            status="success", attempts=1,
        )
        session.add(se)
        await session.commit()
    return {"run_id": run_id, "doc_id": doc_id}


@pytest.mark.asyncio
async def test_runs_list_shows_run(runner, seeded_run, db_url):
    result = runner.invoke(app, ["runs", "list", "--db-url", db_url])
    assert result.exit_code == 0, result.output
    assert str(seeded_run["run_id"])[:8] in result.output


@pytest.mark.asyncio
async def test_runs_list_json(runner, seeded_run, db_url):
    result = runner.invoke(app, ["runs", "list", "--json", "--db-url", db_url])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "run_id" in data[0]


@pytest.mark.asyncio
async def test_runs_show_happy_path(runner, seeded_run, db_url):
    run_id = str(seeded_run["run_id"])
    result = runner.invoke(app, ["runs", "show", run_id, "--db-url", db_url])
    assert result.exit_code == 0, result.output
    assert run_id[:8] in result.output


@pytest.mark.asyncio
async def test_runs_show_missing_run_exits_1(runner, db_url):
    result = runner.invoke(app, ["runs", "show", str(uuid.uuid4()), "--db-url", db_url])
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_runs_show_json(runner, seeded_run, db_url):
    run_id = str(seeded_run["run_id"])
    result = runner.invoke(app, ["runs", "show", run_id, "--json", "--db-url", db_url])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["run_id"] == run_id
    assert "agent_runs" in data
    assert "span_extractions" in data
