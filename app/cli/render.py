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
    if status in {"embedded", "claims_extracted"}:
        return "green"
    if status in {"fetched", "chunked", "extraction_partial"}:
        return "yellow"
    return "red"


def render_extraction_summary(summary: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        _print_json(summary)
        return

    table = Table(title="Extraction Summary", show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Claims extracted", str(summary.get("claims_extracted", 0)))
    table.add_row("Spans processed", str(summary.get("spans_processed", 0)))
    table.add_row("Spans failed", str(summary.get("spans_failed", 0)))
    table.add_row("Tokens used", str(summary.get("tokens_used", 0)))
    cost = summary.get("cost_estimate_usd", 0.0)
    table.add_row("Cost estimate", f"${cost:.6f}")
    console.print(table)


def render_claims_table(claims: list[dict[str, Any]], *, json_output: bool) -> None:
    if json_output:
        _print_json(claims)
        return
    if not claims:
        console.print("[dim]No claims found.[/dim]")
        return

    table = Table(title=f"Claims ({len(claims)})", show_header=True, header_style="bold")
    table.add_column("Type")
    table.add_column("Conf", justify="right")
    table.add_column("Entities")
    table.add_column("Claim")

    for c in claims:
        conf = c.get("confidence")
        conf_str = f"{conf:.2f}" if conf is not None else ""
        conf_color = "green" if (conf or 0) >= 0.8 else "yellow" if (conf or 0) >= 0.5 else "white"
        entities = ", ".join(c.get("entities_json") or [])
        table.add_row(
            _short(c.get("claim_type") or "", 20),
            f"[{conf_color}]{conf_str}[/{conf_color}]",
            _short(entities, 30),
            _short(c.get("claim_text") or "", 80),
        )
    console.print(table)


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
    sources_line = (
        f"{snapshot.get('total_sources', 0)} ({snapshot.get('enabled_sources', 0)} enabled)"
    )
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


def render_document_detail(
    detail: dict[str, Any],
    *,
    json_output: bool,
    claims: list[dict[str, Any]] | None = None,
) -> None:
    if json_output:
        out = dict(detail)
        if claims is not None:
            out["claims"] = claims
        _print_json(out)
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
    else:
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

    if claims is not None:
        render_claims_table(claims, json_output=False)


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
    table.add_column("Doc Status")
    table.add_column("Title")
    table.add_column("Preview")

    for rank, r in enumerate(results, start=1):
        score = r.get("score", 0.0)
        score_color = "green" if score >= 0.7 else "yellow" if score >= 0.5 else "white"
        doc_status = r.get("document_status") or ""
        status_color = _status_color(doc_status) if doc_status else "white"
        table.add_row(
            str(rank),
            f"[{score_color}]{score:.3f}[/{score_color}]",
            f"[{status_color}]{doc_status}[/{status_color}]" if doc_status else "",
            _short(r.get("document_title") or "", 30),
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


def render_runs_list(runs: list[dict[str, Any]], *, json_output: bool = False) -> None:
    if json_output:
        _print_json(runs)
        return
    if not runs:
        console.print("[dim]No extraction runs found.[/dim]")
        return
    table = Table(title="Extraction Runs", show_lines=False, show_header=True, header_style="bold")
    table.add_column("run_id", style="cyan")
    table.add_column("document_id")
    table.add_column("model")
    table.add_column("LLM calls", justify="right")
    table.add_column("cost $", justify="right")
    table.add_column("started_at")
    table.add_column("ok?")
    for r in runs:
        table.add_row(
            _short(r.get("run_id"), 9),
            _short(r.get("document_id"), 9) or "—",
            str(r.get("model") or "—"),
            str(r.get("llm_calls", "")),
            f"{float(r.get('total_cost') or 0):.5f}",
            _short(r.get("started_at"), 19) or "—",
            "✓" if r.get("all_success") else "✗",
        )
    console.print(table)


def render_run_detail(detail: dict[str, Any], *, json_output: bool = False) -> None:
    if json_output:
        _print_json(detail)
        return
    doc = detail.get("document") or {}
    console.print(f"[bold]Run:[/bold] {detail['run_id'][:8]}")
    if doc:
        console.print(f"[bold]Document:[/bold] {_short(doc.get('id'), 8)} — status: {doc.get('status')}")
        console.print(f"  extraction_started_at:   {doc.get('extraction_started_at')}")
        console.print(f"  extraction_completed_at: {doc.get('extraction_completed_at')}")

    ar_table = Table(title="LLM Calls (agent_runs)", show_lines=False, show_header=True, header_style="bold")
    ar_table.add_column("span_id")
    ar_table.add_column("status")
    ar_table.add_column("prompt_tok", justify="right")
    ar_table.add_column("comp_tok", justify="right")
    ar_table.add_column("created_at")
    for r in detail.get("agent_runs", []):
        ar_table.add_row(
            _short(r.get("span_id"), 8) or "—",
            str(r.get("status", "")),
            str(r.get("prompt_tokens") or "—"),
            str(r.get("completion_tokens") or "—"),
            _short(r.get("created_at"), 19),
        )
    console.print(ar_table)

    se_table = Table(title="Span Extractions", show_lines=False, show_header=True, header_style="bold")
    se_table.add_column("span_id")
    se_table.add_column("status")
    se_table.add_column("attempts", justify="right")
    se_table.add_column("error")
    for r in detail.get("span_extractions", []):
        se_table.add_row(
            _short(r.get("span_id"), 8),
            str(r.get("status", "")),
            str(r.get("attempts", "")),
            str(r.get("error") or "—"),
        )
    console.print(se_table)
