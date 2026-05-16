"""Rich + JSON formatters for CLI output. All functions print to stdout."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


def _to_jsonable(value: Any) -> Any:
    """Convert UUIDs and datetimes to JSON-serialisable forms."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _print_json(data: Any) -> None:
    print(json.dumps(_to_jsonable(data), indent=2, default=str))


def _short(value: Any, n: int) -> str:
    s = "" if value is None else str(value)
    return s if len(s) <= n else s[: n - 1] + "…"


def _status_color(status: str) -> str:
    if status == "embedded":
        return "green"
    if status in {"fetched", "chunked"}:
        return "yellow"
    return "red"


def render_status(snapshot: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        _print_json(snapshot)
        return

    table = Table(title="Pipeline Status", show_header=True, header_style="bold")
    table.add_column("Stage")
    table.add_column("Count", justify="right")

    by_status = snapshot.get("docs_by_status") or {}
    stuck = snapshot.get("stuck_count", 0) > 0
    for stage in ("fetched", "chunked", "embedded"):
        count = by_status.get(stage, 0)
        color = "yellow" if (stage in {"fetched", "chunked"} and stuck) else _status_color(stage)
        table.add_row(f"[{color}]{stage}[/{color}]", str(count))

    table.add_section()
    table.add_row("Total docs", str(snapshot.get("total_documents", 0)))
    table.add_row("Total spans", str(snapshot.get("total_spans", 0)))
    sources_line = f"{snapshot.get('total_sources', 0)} ({snapshot.get('enabled_sources', 0)} enabled)"
    table.add_row("Sources", sources_line)

    last = snapshot.get("last_ingest_at")
    last_str = last.isoformat() if last else "never"
    table.add_row("Last ingest", last_str)

    console.print(table)


def render_sources_table(sources: list[dict[str, Any]], *, json_output: bool) -> None:
    if json_output:
        _print_json(sources)
        return
    if not sources:
        console.print("[dim]No sources configured.[/dim]")
        return

    table = Table(title="Sources", show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("URL")
    table.add_column("Domain")
    table.add_column("Enabled")
    table.add_column("Cred", justify="right")

    for s in sources:
        enabled_mark = "[green]✓[/green]" if s["enabled"] else "[red]✗[/red]"
        table.add_row(
            _short(s["id"], 8),
            _short(s["name"], 30),
            s["source_type"],
            _short(s.get("url") or "", 50),
            s["domain_pack"],
            enabled_mark,
            f"{s['credibility_score']:.2f}",
        )
    console.print(table)


def render_documents_table(documents: list[dict[str, Any]], *, json_output: bool) -> None:
    if json_output:
        _print_json(documents)
        return
    if not documents:
        console.print("[dim]No documents found.[/dim]")
        return

    table = Table(title="Documents", show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Fetched At")

    for d in documents:
        status = d["status"]
        color = _status_color(status)
        fetched_str = d["fetched_at"].isoformat() if d.get("fetched_at") else ""
        table.add_row(
            _short(d["id"], 8),
            _short(d.get("title") or "(no title)", 40),
            _short(d.get("source_name") or "", 20),
            f"[{color}]{status}[/{color}]",
            _short(fetched_str, 25),
        )
    console.print(table)


def render_document_detail(detail: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        _print_json(detail)
        return

    meta = Table(title=f"Document {_short(detail['id'], 8)}", show_header=False)
    meta.add_column("Field", style="bold")
    meta.add_column("Value")
    meta.add_row("Title", detail.get("title") or "(no title)")
    meta.add_row("URL", detail.get("url") or "(none)")
    meta.add_row("Source", detail.get("source_name") or "")
    color = _status_color(detail["status"])
    meta.add_row("Status", f"[{color}]{detail['status']}[/{color}]")
    meta.add_row("Content hash", _short(detail["content_hash"], 16))
    if detail.get("published_at"):
        meta.add_row("Published", detail["published_at"].isoformat())
    if detail.get("fetched_at"):
        meta.add_row("Fetched", detail["fetched_at"].isoformat())
    console.print(meta)

    spans = detail.get("spans") or []
    if not spans:
        console.print("[dim]No spans yet.[/dim]")
        return

    span_table = Table(title=f"Spans ({len(spans)})", show_header=True, header_style="bold")
    span_table.add_column("Index", justify="right")
    span_table.add_column("Tokens", justify="right")
    span_table.add_column("Embedding")
    span_table.add_column("Preview")
    for s in spans:
        emb = "[green]vec(384)[/green]" if s.get("has_embedding") else "[yellow]none[/yellow]"
        span_table.add_row(
            str(s["span_index"]),
            str(s.get("token_count") or ""),
            emb,
            _short(s["text"], 80),
        )
    console.print(span_table)


def render_search_results(results: list[dict[str, Any]], *, json_output: bool) -> None:
    if json_output:
        _print_json(results)
        return
    if not results:
        console.print("[dim]No matching spans.[/dim]")
        return

    table = Table(title="Search Results", show_header=True, header_style="bold")
    table.add_column("Rank", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Source")
    table.add_column("Title")
    table.add_column("Preview")

    for rank, r in enumerate(results, start=1):
        score = r.get("score", 0.0)
        score_color = "green" if score >= 0.7 else "yellow" if score >= 0.5 else "white"
        meta = r.get("metadata") or {}
        table.add_row(
            str(rank),
            f"[{score_color}]{score:.3f}[/{score_color}]",
            _short(meta.get("source_name") or "", 20),
            _short(meta.get("title") or "", 30),
            _short(r.get("text") or "", 100),
        )
    console.print(table)


def print_ingest_result(result: dict[str, Any], *, json_output: bool) -> None:
    """Print the result of an ingest command (url/text/rss)."""
    if json_output:
        _print_json(result)
    else:
        import typer
        typer.echo(f"Ingested: {result['ingested']}, Skipped: {result['skipped']}")
