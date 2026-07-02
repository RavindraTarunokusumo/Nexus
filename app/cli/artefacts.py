"""nexus artefacts sub-commands — manual DecisionArtefact creation."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Optional

import typer
from rich.console import Console

from app.cli.capsules import _require_db_url
from app.cli.config import CLISettings
from app.db.session import make_engine, make_session_factory
from app.intelligence.decision_artefacts import build_decision_artefact_row

console = Console()
artefacts_app = typer.Typer(help="DecisionArtefact management commands.")


@artefacts_app.command("create")
def create(
    domain: str = typer.Option(..., "--domain", help="Domain pack id."),
    question: str = typer.Option(..., "--question", help="Question this artefact answers."),
    answer: str = typer.Option(..., "--answer", help="Answer text."),
    capsule_id: list[str] = typer.Option(
        [], "--capsule-id", help="Linked capsule UUID (repeatable)."
    ),
    thesis_id: list[str] = typer.Option([], "--thesis-id", help="Linked thesis UUID (repeatable)."),
    db_url: Optional[str] = typer.Option(None, "--db-url", help="Override DATABASE_URL."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
) -> None:
    """Manually create a `memo`-type DecisionArtefact linking capsules/theses."""
    linked_thesis_ids: list[uuid.UUID] = []
    for t in thesis_id:
        try:
            linked_thesis_ids.append(uuid.UUID(t))
        except ValueError:
            raise typer.BadParameter(f"Invalid UUID for --thesis-id: {t!r}") from None

    linked_capsule_ids: list[uuid.UUID] = []
    for c in capsule_id:
        try:
            linked_capsule_ids.append(uuid.UUID(c))
        except ValueError:
            raise typer.BadParameter(f"Invalid UUID for --capsule-id: {c!r}") from None

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    engine = make_engine(database_url)
    sf = make_session_factory(engine)

    artefact_id = uuid.uuid4()
    artefact = build_decision_artefact_row(
        artefact_id=artefact_id,
        artefact_type="memo",
        domain=domain,
        question=question,
        answer=answer,
        linked_thesis_ids=linked_thesis_ids,
        linked_capsule_ids=linked_capsule_ids,
        source_refs=[],
        created_by_tier="t2",
    )

    async def _run() -> None:
        async with sf() as session:
            session.add(artefact)
            await session.commit()

    asyncio.run(_run())

    if json_output:
        typer.echo(json.dumps({"artefact_id": str(artefact_id)}, indent=2))
    else:
        console.print(f"Created decision artefact [bold]{artefact_id}[/bold]")
