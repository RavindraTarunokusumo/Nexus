# app/cli/eval.py
"""nexus eval sub-commands — run, show, diff, register-dataset, calibrate."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from app.cli.config import CLISettings
from app.db.models import EvalDataset as EvalDatasetModel
from app.db.models import EvalResult, EvalRun
from app.db.session import make_engine, make_session_factory
from app.evaluation.datasets import load_dataset
from app.evaluation.meta_eval import compute_kappa, compute_pearson, load_human_labels
from app.evaluation.runner import SUTConfig, execute_run
from app.intelligence.llm_client import LLMClient

console = Console()
eval_app = typer.Typer(help="LLM-as-a-Judge evaluation commands.")


def _get_session_factory(db_url: str):
    engine = make_engine(db_url)
    return make_session_factory(engine)


_VALID_DB_SCHEMES = ("postgresql://", "postgresql+asyncpg://", "postgresql+psycopg2://")


def _require_db_url(cfg: CLISettings) -> str:
    url = cfg.database_url.strip()
    if not url:
        typer.echo(
            "DATABASE_URL is required for eval commands. Set it in .env or pass --db-url.",
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


@eval_app.command("register-dataset")
def register_dataset(
    path: Path = typer.Argument(..., help="Path to gold-set YAML file."),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
) -> None:
    """Register a gold-set YAML file into eval_datasets."""
    import asyncio

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    sf = _get_session_factory(database_url)

    ds = load_dataset(path)

    async def _insert() -> str:
        async with sf() as session:
            stmt = select(EvalDatasetModel).where(
                EvalDatasetModel.name == ds.name,
                EvalDatasetModel.task == ds.task.value,
                EvalDatasetModel.version == ds.version,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                existing.checksum = ds.checksum
                existing.example_count = len(ds.examples)
                existing.path = str(path.resolve())
                await session.commit()
                return f"Updated: {ds.name} (task={ds.task.value}, v{ds.version})"
            session.add(
                EvalDatasetModel(
                    name=ds.name,
                    task=ds.task,
                    version=ds.version,
                    checksum=ds.checksum,
                    example_count=len(ds.examples),
                    path=str(path.resolve()),
                )
            )
            await session.commit()
            return f"Registered: {ds.name} (task={ds.task.value}, v{ds.version}, {len(ds.examples)} examples)"

    msg = asyncio.run(_insert())
    typer.echo(msg)


@eval_app.command("list-datasets")
def list_datasets(
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List all registered gold-set datasets."""
    import asyncio

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    sf = _get_session_factory(database_url)

    async def _fetch() -> list[dict]:
        async with sf() as session:
            result = await session.execute(
                select(EvalDatasetModel).order_by(EvalDatasetModel.created_at)
            )
            rows = result.scalars().all()
            return [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "task": r.task,
                    "version": r.version,
                    "example_count": r.example_count,
                    "checksum": r.checksum[:12] + "…",
                }
                for r in rows
            ]

    rows = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(rows, indent=2))
        return

    table = Table(title="Registered Eval Datasets")
    for col in ("name", "task", "version", "examples", "checksum"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["task"], str(r["version"]), str(r["example_count"]), r["checksum"]
        )
    console.print(table)


@eval_app.command("run")
def eval_run(
    task: str = typer.Argument(..., help="Task name: claim_extraction"),
    dataset_name: str = typer.Argument(..., help="Dataset name, e.g. ai_tech_v1"),
    dataset_version: int = typer.Option(1, "--version", "-v"),
    dataset_path: Path = typer.Option(..., "--path", help="Path to the gold-set YAML."),
    sut_model: Optional[str] = typer.Option(None, "--sut-model", help="Override T2 model."),
    judge_model: Optional[str] = typer.Option(None, "--judge-model", help="Override T3 judge model."),
    note: Optional[str] = typer.Option(None, "--note"),
    max_cost: float = typer.Option(1.0, "--max-cost", help="Budget gate in USD."),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Execute one eval run and print aggregate scores."""
    import asyncio
    import subprocess

    from app.config import settings as app_settings

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    sf = _get_session_factory(database_url)

    resolved_sut = sut_model or app_settings.t2_model
    resolved_judge = judge_model or app_settings.t3_model

    if max_cost > 50.0:
        raise typer.BadParameter(
            f"--max-cost {max_cost} exceeds the 50 USD safety ceiling. "
            "Pass a value ≤ 50.0 or contact the team to raise the limit.",
            param_hint="--max-cost",
        )

    try:
        prompt_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        prompt_sha = "unknown"

    ds = load_dataset(dataset_path)
    client = LLMClient(api_key=app_settings.openrouter_api_key, session_factory=sf)

    result = asyncio.run(
        execute_run(
            dataset=ds,
            sut_config=SUTConfig(model=resolved_sut, prompt_version=prompt_sha),
            judge_model=resolved_judge,
            judge_prompt_version=prompt_sha,
            session_factory=sf,
            llm_client=client,
            max_cost_usd=max_cost,
            notes=note,
        )
    )

    output = {
        "run_id": str(result.run_id),
        "status": result.status,
        "examples": result.example_count,
        "errors": result.error_count,
        "cost_usd": round(result.total_cost_usd, 4),
        "scores": result.aggregate_scores,
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2))
        return

    typer.echo(f"\n✓ Eval run {result.run_id} [{result.status}]")
    typer.echo(f"  Examples: {result.example_count}  Errors: {result.error_count}  Cost: ${result.total_cost_usd:.4f}")
    for k, v in result.aggregate_scores.items():
        typer.echo(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")


@eval_app.command("show")
def eval_show(
    run_id: str = typer.Argument(..., help="Eval run UUID."),
    per_example: bool = typer.Option(False, "--per-example"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show aggregate scores for an eval run."""
    import asyncio

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    sf = _get_session_factory(database_url)

    async def _fetch():
        async with sf() as session:
            run = await session.get(EvalRun, uuid.UUID(run_id))
            if run is None:
                return None, []
            results = []
            if per_example:
                stmt = select(EvalResult).where(EvalResult.run_id == run.id)
                res = await session.execute(stmt)
                results = [
                    {
                        "example_id": r.example_id,
                        "status": r.status,
                        "metrics": r.deterministic_metrics,
                        "error": r.error_message,
                    }
                    for r in res.scalars().all()
                ]
            return run, results

    run, results = asyncio.run(_fetch())
    if run is None:
        typer.echo(f"Run {run_id} not found.", err=True)
        raise typer.Exit(code=1)

    output = {
        "run_id": str(run.id),
        "status": run.status,
        "sut_model": run.sut_model,
        "judge_model": run.judge_model,
        "aggregate_scores": run.aggregate_scores,
        "total_cost_usd": float(run.total_cost_usd),  # Numeric→Decimal from ORM; cast for json.dumps
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "per_example": results,
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2))
        return

    typer.echo(f"\nRun {run.id}  [{run.status}]")
    typer.echo(f"  SUT: {run.sut_model}  Judge: {run.judge_model}")
    typer.echo(f"  Cost: ${run.total_cost_usd:.4f}  Started: {run.started_at}")
    typer.echo("  Aggregate scores:")
    for k, v in (run.aggregate_scores or {}).items():
        typer.echo(f"    {k}: {v}")
    if per_example:
        typer.echo(f"\n  Per-example results ({len(results)} rows):")
        for r in results:
            typer.echo(f"    [{r['status']}] {r['example_id']}  {r['metrics']}")


@eval_app.command("diff")
def eval_diff(
    run_a: str = typer.Argument(..., help="Baseline run UUID."),
    run_b: str = typer.Argument(..., help="Candidate run UUID."),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Compare aggregate scores between two eval runs."""
    import asyncio

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    sf = _get_session_factory(database_url)

    async def _fetch(rid: str):
        async with sf() as session:
            return await session.get(EvalRun, uuid.UUID(rid))

    a = asyncio.run(_fetch(run_a))
    b = asyncio.run(_fetch(run_b))

    if a is None or b is None:
        typer.echo("One or both run IDs not found.", err=True)
        raise typer.Exit(code=1)

    scores_a = a.aggregate_scores or {}
    scores_b = b.aggregate_scores or {}
    all_keys = sorted(set(scores_a) | set(scores_b))

    output = {
        "run_a": str(a.id),
        "run_b": str(b.id),
        "deltas": {
            k: {
                "a": scores_a.get(k),
                "b": scores_b.get(k),
                "delta": round(scores_b.get(k, 0) - scores_a.get(k, 0), 4)
                if scores_a.get(k) is not None and scores_b.get(k) is not None
                else None,
            }
            for k in all_keys
        },
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2))
        return

    typer.echo(f"\nDiff: {run_a[:8]}… (A) vs {run_b[:8]}… (B)")
    typer.echo(f"{'Metric':<25} {'A':>8} {'B':>8} {chr(916):>8}")
    typer.echo("-" * 55)
    deltas: dict[str, dict[str, float | None]] = output["deltas"]
    for k, vals in deltas.items():
        va = f"{vals['a']:.4f}" if vals["a"] is not None else "—"
        vb = f"{vals['b']:.4f}" if vals["b"] is not None else "—"
        d = f"{vals['delta']:+.4f}" if vals["delta"] is not None else "—"
        typer.echo(f"{k:<25} {va:>8} {vb:>8} {d:>8}")


@eval_app.command("calibrate")
def eval_calibrate(
    task: str = typer.Argument(..., help="Task name: claim_extraction"),
    labels_path: Path = typer.Option(..., "--labels-path", help="Path to human_labels YAML."),
    judge_model: Optional[str] = typer.Option(None, "--judge-model"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Compute Cohen's kappa between judge verdicts and human labels in a YAML file."""
    labels = load_human_labels(labels_path)
    if not labels:
        typer.echo("No labels found in file.", err=True)
        raise typer.Exit(code=1)

    judge_vals = [l["judge_match_status"] for l in labels]
    human_vals = [l["human_match_status"] for l in labels]
    kappa = compute_kappa(judge_vals, human_vals)

    judge_gnd: list[float] = [float(l["judge_groundedness"]) for l in labels if l.get("judge_groundedness") is not None]
    human_gnd: list[float] = [float(l["human_groundedness"]) for l in labels if l.get("human_groundedness") is not None]
    pearson_gnd = compute_pearson(judge_gnd, human_gnd) if len(judge_gnd) > 1 else None

    output = {
        "task": task,
        "n_pairs": len(labels),
        "match_status_kappa": round(kappa, 4),
        "groundedness_pearson_r": round(pearson_gnd, 4) if pearson_gnd is not None else None,
        "recommendation": (
            "PASS (kappa >= 0.6 — judge suitable for gating decisions)"
            if kappa >= 0.6
            else "FAIL (kappa < 0.6 — rewrite judge rubric before using for gating)"
        ),
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2))
        return

    typer.echo(f"\nCalibration: {task}  ({len(labels)} pairs)")
    typer.echo(f"  match_status kappa:     {kappa:.4f}")
    if pearson_gnd is not None:
        typer.echo(f"  groundedness r:     {pearson_gnd:.4f}")
    typer.echo(f"  → {output['recommendation']}")
