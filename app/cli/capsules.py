"""nexus capsules sub-commands — backfill from Phase-A _v0_7 blobs."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.cli.config import CLISettings
from app.db.session import make_engine, make_session_factory
from app.intelligence.backfill import backfill_capsules

console = Console()
capsules_app = typer.Typer(help="SemanticCapsule management commands.")

_VALID_DB_SCHEMES = ("postgresql://", "postgresql+asyncpg://", "postgresql+psycopg2://")


def _require_db_url(cfg: CLISettings) -> str:
    url = (cfg.database_url or "").strip()
    if not url:
        typer.echo(
            "DATABASE_URL is required for capsule commands. Set it in .env or pass --db-url.",
            err=True,
        )
        raise typer.Exit(code=1)
    if not any(url.startswith(s) for s in _VALID_DB_SCHEMES):
        typer.echo(
            f"--db-url must start with one of: {', '.join(_VALID_DB_SCHEMES)}",
            err=True,
        )
        raise typer.Exit(code=1)
    return url


@capsules_app.command("backfill")
def backfill(
    dry_run: bool = typer.Option(False, "--dry-run", help="Report counts without writing."),
    batch_size: int = typer.Option(500, "--batch-size", help="Claims per page query."),
    db_url: Optional[str] = typer.Option(None, "--db-url", help="Override DATABASE_URL."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
) -> None:
    """Backfill SemanticCapsule rows from Phase-A _v0_7 blobs in claims.entities_json.

    Reads every Claim row that has an entities_json['_v0_7'] key (written by
    Phase A's projection layer) and constructs the corresponding SemanticCapsule
    + CapsuleSegment rows. Idempotent: re-runs skip claims whose capsule already
    exists (detected via the shared idempotency_key).

    Use --dry-run to see what would be written without committing any rows.
    """
    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)

    engine = make_engine(database_url)
    sf = make_session_factory(engine)

    result = asyncio.run(backfill_capsules(sf, dry_run=dry_run, batch_size=batch_size))

    output = {
        "dry_run": dry_run,
        "claims_scanned": result.claims_scanned,
        "claims_skipped_no_v07": result.claims_skipped_no_v07,
        "claims_skipped_already_backfilled": result.claims_skipped_already_backfilled,
        "capsules_written": result.capsules_written,
        "capsule_segments_written": result.capsule_segments_written,
        "errors": result.errors,
    }

    if json_output:
        typer.echo(json.dumps(output, indent=2))
        return

    label = " (DRY RUN — no rows committed)" if dry_run else ""
    table = Table(title=f"Capsule Backfill{label}")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")

    table.add_row("Claims scanned", str(result.claims_scanned))
    table.add_row("Skipped — no _v0_7 key", str(result.claims_skipped_no_v07))
    table.add_row("Skipped — already backfilled", str(result.claims_skipped_already_backfilled))
    table.add_row(
        "Capsules written" + (" (would write)" if dry_run else ""),
        str(result.capsules_written),
    )
    table.add_row(
        "Capsule segments written" + (" (would write)" if dry_run else ""),
        str(result.capsule_segments_written),
    )
    if result.errors:
        table.add_row("Errors", str(len(result.errors)), style="red")

    console.print(table)

    for err in result.errors:
        typer.echo(f"  ERROR: {err}", err=True)
