"""Phase 2 validation harness.

Exercises the five primary CLI paths end-to-end:
  1. Text ingest
  2. RSS ingest
  3. Status command
  4. Document inspection (with claims)
  5. Semantic search

Each test uses the shared clean_db autouse fixture (truncates all tables
before every test) so they are fully independent.

Marked @pytest.mark.slow — skipped in fast-unit CI via:
  pytest -m "not slow"
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from app.db.models import Claim, Document, Source

runner = CliRunner()

pytestmark = pytest.mark.slow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_source_and_doc(session_factory, *, status: str = "fetched") -> tuple:
    async with session_factory() as session:
        src = Source(
            name="Validation Feed",
            source_type="rss",
            url=f"https://val-{uuid.uuid4()}.example/feed",
            domain_pack="personal_ai_tech",
        )
        session.add(src)
        await session.flush()
        doc = Document(
            source_id=src.id,
            title="Validation Article",
            clean_text="Some article text.",
            content_hash=f"h-val-{uuid.uuid4()}",
            status=status,
        )
        session.add(doc)
        await session.commit()
        return src.id, doc.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_ingest_path(monkeypatch, db_url):
    """nexus ingest text → CliRunner exits 0 and the HTTP helper is called."""
    captured: dict = {}

    async def fake_ingest_text(base_url, *, title, text, source_name, domain_pack):
        captured.update(title=title, text=text)
        return {
            "ingested": 1,
            "skipped": 0,
            "documents": [{"id": str(uuid.uuid4()), "title": title}],
        }

    monkeypatch.setattr("app.cli.main.http_ingest_text", fake_ingest_text)

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    try:
        tmp.write("Direct article body.")
        tmp.close()
        result = runner.invoke(
            app,
            [
                "ingest",
                "text",
                "--title",
                "Test Article",
                "--file",
                tmp.name,
                "--api-url",
                "http://test.example",
            ],
        )
    finally:
        os.unlink(tmp.name)

    assert result.exit_code == 0, result.stdout
    assert captured["title"] == "Test Article"
    assert captured["text"] == "Direct article body."


@pytest.mark.asyncio
async def test_rss_ingest_path(monkeypatch, db_url, session_factory):
    """nexus ingest rss <source_id> → CliRunner exits 0 and reports counts."""
    src_id, _ = await _seed_source_and_doc(session_factory)
    captured: dict = {}

    async def fake_ingest_rss(base_url, source_id):
        captured["source_id"] = source_id
        return {"ingested": 2, "skipped": 1, "documents": []}

    monkeypatch.setattr("app.cli.main.http_ingest_rss", fake_ingest_rss)

    result = runner.invoke(
        app,
        ["ingest", "rss", str(src_id), "--api-url", "http://test.example"],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["source_id"] == src_id


@pytest.mark.asyncio
async def test_status_path(session_factory, db_url):
    """nexus status --json reflects exact document counts from DB seed."""
    _, _ = await _seed_source_and_doc(session_factory, status="embedded")
    async with session_factory() as session:
        src = Source(
            name="Feed 2",
            source_type="rss",
            url=f"https://val2-{uuid.uuid4()}.example/feed",
            domain_pack="personal_ai_tech",
        )
        session.add(src)
        await session.flush()
        doc2 = Document(
            source_id=src.id,
            title="Doc 2",
            clean_text="y",
            content_hash=f"h-val2-{uuid.uuid4()}",
            status="fetched",
        )
        session.add(doc2)
        await session.commit()

    result = runner.invoke(app, ["status", "--json", "--db-url", db_url])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["total_documents"] == 2
    assert data["docs_by_status"]["embedded"] == 1
    assert data["docs_by_status"]["fetched"] == 1


@pytest.mark.asyncio
async def test_document_inspection_path(session_factory, db_url):
    """nexus document <id> --claims --json returns title and attached claims."""
    _, doc_id = await _seed_source_and_doc(session_factory, status="claims_extracted")
    async with session_factory() as session:
        session.add(
            Claim(
                document_id=doc_id,
                claim_text="GPT-5 released.",
                claim_type="model_release",
                entities_json=["OpenAI"],
                topics_json=[],
                confidence=0.9,
                status="active",
            )
        )
        await session.commit()

    result = runner.invoke(
        app,
        ["document", str(doc_id), "--claims", "--json", "--db-url", db_url],
    )
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["title"] == "Validation Article"
    assert len(data["claims"]) == 1
    assert data["claims"][0]["claim_text"] == "GPT-5 released."


@pytest.mark.asyncio
async def test_semantic_search_path(monkeypatch, db_url):
    """nexus search → monkeypatched HTTP round-trip returns correct payload."""
    captured: dict = {}

    async def fake_search(base_url, query, top_k):
        captured.update(query=query, top_k=top_k)
        return [
            {
                "span_id": str(uuid.uuid4()),
                "document_id": str(uuid.uuid4()),
                "span_index": 0,
                "score": 0.88,
                "text": "Validation span text.",
                "document_title": "Validation Article",
                "document_status": "claims_extracted",
            }
        ]

    monkeypatch.setattr("app.cli.main.http_search_spans", fake_search)

    result = runner.invoke(
        app,
        [
            "search",
            "AI safety research",
            "--top-k",
            "3",
            "--json",
            "--api-url",
            "http://test.example",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["query"] == "AI safety research"
    assert captured["top_k"] == 3
    data = json.loads(result.stdout)
    assert data[0]["score"] == pytest.approx(0.88)
