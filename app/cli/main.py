"""Nexus CLI — typer App entry point."""

from __future__ import annotations

import asyncio
import concurrent.futures
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import typer

from app.cli.config import CLISettings
from app.cli.db import (
    get_claims_for_document,
    get_document_with_spans,
    get_status_snapshot,
    list_documents,
    list_runs,
    list_sources,
    show_run,
)
from app.cli.http import (
    CLIHttpError,
)
from app.cli.http import (
    extract_claims as http_extract_claims,
)
from app.cli.http import (
    ingest_rss as http_ingest_rss,
)
from app.cli.http import (
    ingest_text as http_ingest_text,
)
from app.cli.http import (
    ingest_url as http_ingest_url,
)
from app.cli.http import (
    search_spans as http_search_spans,
)
from app.cli.render import (
    print_ingest_result,
    render_document_detail,
    render_documents_table,
    render_extraction_summary,
    render_run_detail,
    render_runs_list,
    render_search_results,
    render_sources_table,
    render_status,
)
from app.observability.logger import configure_logging

configure_logging()

app = typer.Typer(help="Nexus Lite — operator CLI for monitoring the system.")
ingest_app = typer.Typer(help="Trigger ingestion via the running server.")
app.add_typer(ingest_app, name="ingest")
runs_app = typer.Typer(help="Query extraction run traces.")
app.add_typer(runs_app, name="runs")

from app.cli.eval import eval_app  # noqa: E402
app.add_typer(eval_app, name="eval")


def _run(coro):
    """Run a coroutine safely — works both inside and outside a running event loop.

    When pytest-asyncio (or any other framework) already owns the event loop,
    ``asyncio.run()`` raises RuntimeError.  Running the coroutine in a fresh
    daemon thread guarantees it always gets its own loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


def _run_http(coro):
    """Run an HTTP coroutine and surface network/API errors as clean Typer exits."""
    try:
        return _run(coro)
    except CLIHttpError as exc:
        typer.echo(f"API error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    except httpx.HTTPError as exc:
        typer.echo(f"Network error: {exc}", err=True)
        raise typer.Exit(code=1) from None


def _settings(db_url: Optional[str], api_url: Optional[str]) -> CLISettings:
    overrides = {}
    if db_url:
        overrides["database_url"] = db_url
    if api_url:
        overrides["api_base_url"] = api_url
    return CLISettings(**overrides) if overrides else CLISettings()


def _require_db_url(cfg: CLISettings) -> str:
    """Enforce database_url for commands that read from Postgres directly."""
    if not cfg.database_url:
        typer.echo("DATABASE_URL is not set. Set it in .env or pass --db-url.", err=True)
        raise typer.Exit(code=1)
    return cfg.database_url


def _parse_since(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid --since value '{value}': {exc}") from exc


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
    db_url: Optional[str] = typer.Option(None, "--db-url", help="Override DATABASE_URL."),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="Override API base URL."),
) -> None:
    """Show pipeline health: counts by status, totals, last ingest."""
    cfg = _settings(db_url, api_url)
    database_url = _require_db_url(cfg)
    snapshot = _run(get_status_snapshot(database_url))
    render_status(snapshot, json_output=json_output)


@app.command()
def sources(
    enabled: Optional[bool] = typer.Option(
        None, "--enabled/--disabled", help="Filter by enabled flag."
    ),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """List configured sources."""
    cfg = _settings(db_url, api_url)
    database_url = _require_db_url(cfg)
    result = _run(list_sources(database_url, enabled=enabled))
    render_sources_table(result, json_output=json_output)


@app.command()
def documents(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by document status."),
    source_id: Optional[uuid.UUID] = typer.Option(None, "--source", help="Filter by source ID."),
    since: Optional[str] = typer.Option(
        None, "--since", help="Only docs fetched after ISO timestamp."
    ),
    limit: int = typer.Option(50, "--limit"),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """List documents with optional filters."""
    since_dt = _parse_since(since)
    cfg = _settings(db_url, api_url)
    database_url = _require_db_url(cfg)
    docs = _run(
        list_documents(
            database_url,
            status=status,
            source_id=source_id,
            since=since_dt,
            limit=limit,
        )
    )
    render_documents_table(docs, json_output=json_output)


@app.command()
def document(
    document_id: uuid.UUID = typer.Argument(..., help="Document UUID."),
    show_claims: bool = typer.Option(False, "--claims", help="Also show extracted claims."),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Show one document and all its spans."""
    cfg = _settings(db_url, api_url)
    database_url = _require_db_url(cfg)
    detail = _run(get_document_with_spans(database_url, document_id))
    if detail is None:
        typer.echo(f"Document {document_id} not found.", err=True)
        raise typer.Exit(code=1)
    claims = _run(get_claims_for_document(database_url, document_id)) if show_claims else None
    render_document_detail(detail, json_output=json_output, claims=claims)


@app.command()
def extract(
    document_id: uuid.UUID = typer.Argument(..., help="Document UUID to extract claims from."),
    force: bool = typer.Option(False, "--force", help="Re-extract even if claims already exist."),
    json_output: bool = typer.Option(False, "--json"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="Override API base URL."),
) -> None:
    """Run claim extraction for a document via the API."""
    cfg = _settings(None, api_url)
    summary = _run_http(http_extract_claims(cfg.api_base_url, document_id, force=force))
    render_extraction_summary(summary, json_output=json_output)


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language search query."),
    top_k: int = typer.Option(10, "--top-k"),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Semantic search over embedded spans."""
    cfg = _settings(db_url, api_url)
    results = _run_http(http_search_spans(cfg.api_base_url, query, top_k))
    render_search_results(results, json_output=json_output)


@runs_app.command("list")
def runs_list(
    limit: int = typer.Option(50, "--limit"),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """List recent extraction runs."""
    cfg = _settings(db_url, api_url)
    database_url = _require_db_url(cfg)
    result = _run(list_runs(database_url, limit=limit))
    render_runs_list(result, json_output=json_output)


@runs_app.command("show")
def runs_show(
    run_id: str = typer.Argument(..., help="Run UUID to inspect."),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Show full trace for one extraction run."""
    cfg = _settings(db_url, api_url)
    database_url = _require_db_url(cfg)
    detail = _run(show_run(database_url, run_id))
    if detail is None:
        typer.echo(f"Run {run_id} not found.", err=True)
        raise typer.Exit(code=1)
    render_run_detail(detail, json_output=json_output)


@ingest_app.command("url")
def ingest_url_cmd(
    url: str = typer.Argument(..., help="URL to fetch and ingest."),
    source_name: str = typer.Option("manual", "--source-name"),
    domain_pack: str = typer.Option("personal_ai_tech", "--domain-pack"),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Fetch one URL and ingest its content."""
    cfg = _settings(db_url, api_url)
    result = _run_http(http_ingest_url(cfg.api_base_url, url, source_name, domain_pack))
    print_ingest_result(result, json_output=json_output)


@ingest_app.command("text")
def ingest_text_cmd(
    title: str = typer.Option(..., "--title", help="Document title."),
    file: str = typer.Option(..., "--file", help="Path to text/markdown file."),
    source_name: str = typer.Option("manual", "--source-name"),
    domain_pack: str = typer.Option("personal_ai_tech", "--domain-pack"),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Ingest the contents of a local text file."""
    text = Path(file).read_text(encoding="utf-8")
    cfg = _settings(db_url, api_url)
    result = _run_http(
        http_ingest_text(
            cfg.api_base_url,
            title=title,
            text=text,
            source_name=source_name,
            domain_pack=domain_pack,
        )
    )
    print_ingest_result(result, json_output=json_output)


@ingest_app.command("rss")
def ingest_rss_cmd(
    source_id: uuid.UUID = typer.Argument(..., help="Source UUID (must be source_type=rss)."),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Trigger RSS ingestion for a configured source."""
    cfg = _settings(db_url, api_url)
    result = _run_http(http_ingest_rss(cfg.api_base_url, source_id))
    print_ingest_result(result, json_output=json_output)
