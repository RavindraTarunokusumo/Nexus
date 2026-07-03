"""CLI smoke tests for `nexus relations run`."""

from __future__ import annotations

import json
import re

from typer.testing import CliRunner

from app.cli.main import app
from app.intelligence.cross_relations import CrossDocReport

runner = CliRunner()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_relations_help_works():
    result = runner.invoke(app, ["relations", "--help"])
    assert result.exit_code == 0
    assert "relations" in result.stdout.lower()


def test_relations_run_help_works():
    result = runner.invoke(app, ["relations", "run", "--help"])
    assert result.exit_code == 0
    assert "-domain" in _strip_ansi(result.stdout)


def test_relations_run_defaults_domain_to_pack(monkeypatch, db_url):
    captured: dict = {}

    async def fake_classify(*args, **kwargs):
        captured.update(kwargs)
        return CrossDocReport(
            candidate_pairs=0, classified_pairs=0, relation_ids=[], skipped_existing=0
        )

    monkeypatch.setattr(
        "app.cli.relations.classify_cross_document_relations",
        fake_classify,
    )

    result = runner.invoke(app, ["relations", "run", "--json", "--db-url", db_url])
    assert result.exit_code == 0, result.stdout
    from app.config import settings
    from app.domain_packs.loader import load_pack

    assert captured["domain"] == load_pack(settings.default_pack_id).metadata.domain


def test_relations_run_json_zero_counts(monkeypatch, db_url):
    report = CrossDocReport(
        candidate_pairs=0,
        classified_pairs=0,
        relations_created=0,
        relation_ids=[],
        skipped_existing=0,
    )

    async def fake_classify(*args, **kwargs):
        return report

    monkeypatch.setattr(
        "app.cli.relations.classify_cross_document_relations",
        fake_classify,
    )

    result = runner.invoke(
        app,
        ["relations", "run", "--domain", "ai_tech", "--json", "--db-url", db_url],
    )
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["candidate_pairs"] == 0
    assert data["classified_pairs"] == 0
    assert data["relations_created"] == 0
    assert data["skipped_existing"] == 0
    assert data["relation_ids"] == []
