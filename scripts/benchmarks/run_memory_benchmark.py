"""Memory benchmark runner (T-F35): ingest fixtures, run lifecycle/consolidation,
answer questions through the real chat graph, and score against expected keywords.

Importable entry point: ``run_benchmark`` (async). Does not require the FastAPI
server — builds its own session_factory from ``settings.database_url``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.routes_ingestion import (
    _chunk_and_embed,
    _get_or_create_manual_source,
    _persist_document,
)
from app.config import settings
from app.db.models import Document
from app.db.session import make_engine, make_session_factory
from app.domain_packs.loader import load_pack
from app.ingestion.cleaner import normalize_url
from app.intelligence.chat import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    make_chat_graph,
    run_chat_with_context,
)
from app.intelligence.consolidation import consolidate_domain
from app.intelligence.cross_relations import classify_cross_document_relations
from app.intelligence.embedder import Embedder
from app.intelligence.extraction import _resolve_t2_model, make_extraction_graph, run_with_context
from app.intelligence.lifecycle import apply_lifecycle_transitions
from app.intelligence.llm_client import LLMClient
from scripts.benchmarks.scoring import METRIC_KEYS, aggregate, score_answer

_DEFAULT_FIXTURES = Path("evals/memory/nexus_synthetic")
_SOURCE_NAME = "benchmark"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _git_rev() -> str:
    try:
        return subprocess.check_output(  # noqa: S603
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        ).strip()
    except Exception:  # noqa: BLE001 — best-effort only
        return "unknown"


async def _ingest_corpus(
    corpus: list[dict[str, Any]],
    session_factory: async_sessionmaker,
    embedder: Any,
    domain_pack_id: str,
) -> tuple[int, int]:
    """Idempotent-by-URL ingest + chunk/embed. Returns (ingested, skipped)."""
    async with session_factory() as session:
        source = await _get_or_create_manual_source(
            session, name=_SOURCE_NAME, domain_pack=domain_pack_id
        )
        await session.commit()
        source_id = source.id

    ingested = 0
    skipped = 0
    new_doc_ids: list[uuid.UUID] = []
    for doc in corpus:
        async with session_factory() as session:
            persisted = await _persist_document(
                session,
                source_id=source_id,
                title=doc["title"],
                url=doc["url"],
                raw_text=doc["text"],
                clean_text=doc["text"],
                published_at=_parse_iso8601(doc["published_at"]),
            )
            if persisted is None:
                skipped += 1
                continue
            await session.commit()
            await session.refresh(persisted)
            new_doc_ids.append(persisted.id)
            ingested += 1

    for doc_id in new_doc_ids:
        await _chunk_and_embed(doc_id, session_factory, embedder)

    return ingested, skipped


async def _extract_new_documents(
    corpus: list[dict[str, Any]],
    session_factory: async_sessionmaker,
    client: LLMClient,
    domain_pack_id: str,
) -> None:
    """Run the extraction graph over every corpus doc currently at status 'embedded'.

    Idempotent-by-URL ingestion means already-processed docs are past 'embedded'
    (e.g. 'claims_extracted'); load_spans rejects those with a benign per-doc error.
    """
    graph = make_extraction_graph(session_factory, client)
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Document.id, Document.status).where(
                    Document.url.in_([normalize_url(doc["url"]) for doc in corpus])
                )
            )
        ).all()
    embedded_ids = [row.id for row in rows if row.status == "embedded"]
    for doc_id in embedded_ids:
        await run_with_context(graph, doc_id, settings.t2_model)


def _build_doc_key_index(corpus: list[dict[str, Any]]) -> dict[str, str]:
    return {normalize_url(doc["url"]): doc["doc_key"] for doc in corpus}


def _cited_and_retrieved_doc_keys(
    final_state: dict[str, Any],
    url_to_doc_key: dict[str, str],
) -> tuple[list[str], list[str]]:
    cited_doc_keys = sorted(
        {
            url_to_doc_key[normalize_url(c["url"])]
            for c in final_state.get("citations", [])
            if c.get("url") and normalize_url(c["url"]) in url_to_doc_key
        }
    )
    retrieved_doc_keys = sorted(
        {
            url_to_doc_key[normalize_url(b["url"])]
            for b in final_state.get("context_blocks", [])
            if b.get("url") and normalize_url(b["url"]) in url_to_doc_key
        }
    )
    return cited_doc_keys, retrieved_doc_keys


async def _answer_questions(
    questions: list[dict[str, Any]],
    url_to_doc_key: dict[str, str],
    session_factory: async_sessionmaker,
    client: LLMClient,
    embedder: Any,
    pack: Any,
    k: int,
) -> list[dict[str, Any]]:
    graph = make_chat_graph(session_factory, client, embedder)
    rows: list[dict[str, Any]] = []
    for question in questions:
        start = time.monotonic()
        final = await run_chat_with_context(
            graph, question["question"], settings.t2_model, top_k=k, pack=pack
        )
        latency_s = time.monotonic() - start

        answer = final.get("answer") or INSUFFICIENT_EVIDENCE_ANSWER
        abstained = answer == INSUFFICIENT_EVIDENCE_ANSWER
        cited_doc_keys, retrieved_doc_keys = _cited_and_retrieved_doc_keys(final, url_to_doc_key)
        metrics = score_answer(question, answer, cited_doc_keys, retrieved_doc_keys, abstained)

        rows.append(
            {
                **question,
                "answer": answer,
                "abstained": abstained,
                "cited_doc_keys": cited_doc_keys,
                "retrieved_doc_keys": retrieved_doc_keys,
                "latency_s": latency_s,
                "tokens_used": final.get("tokens_used", 0),
                "question_shape": final.get("question_shape", "general"),
                "query_intent": final.get("query_intent", "general"),
                **metrics,
            }
        )
    return rows


def _write_results(out_dir: Path, rows: list[dict[str, Any]]) -> None:
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _render_report(agg: dict[str, Any]) -> str:
    lines = ["# Memory Benchmark Report", ""]

    def _table(title: str, metrics: dict[str, Any]) -> list[str]:
        block = [f"## {title}", "", "| Metric | Value |", "| --- | --- |"]
        for key, value in metrics.items():
            rendered = f"{value:.3f}" if isinstance(value, float) else str(value)
            block.append(f"| {key} | {rendered} |")
        block.append("")
        return block

    lines += _table("Overall", agg["overall"])
    for category, metrics in agg["by_category"].items():
        lines += _table(f"Category: {category}", metrics)
    return "\n".join(lines)


def _write_report(out_dir: Path, agg: dict[str, Any]) -> None:
    (out_dir / "report.md").write_text(_render_report(agg), encoding="utf-8")


def _write_run_meta(
    out_dir: Path,
    *,
    k: int,
    domain: str,
    doc_count: int,
    question_count: int,
    started_at: datetime,
    finished_at: datetime,
    cross_doc_relations: dict[str, int] | None = None,
) -> None:
    meta = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "git_rev": _git_rev(),
        "domain": domain,
        "k": k,
        "t1_model": settings.t1_model,
        "t2_model": settings.t2_model,
        "t3_model": settings.t3_model,
        "llm_base_url": settings.llm_base_url,
        "doc_count": doc_count,
        "question_count": question_count,
    }
    if cross_doc_relations is not None:
        meta["cross_doc_relations"] = cross_doc_relations
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


async def run_benchmark(
    *,
    fixtures: Path = _DEFAULT_FIXTURES,
    k: int = 5,
    out: Path | None = None,
    skip_ingest: bool = False,
    domain: str | None = None,
) -> dict[str, Any]:
    """Run the full memory benchmark pipeline and write results under *out*.

    Returns a dict with ``out_dir`` (str), ``run_meta`` and ``aggregate`` (F5 metrics).
    """
    started_at = datetime.now(timezone.utc)
    out_dir = out or Path("docs/benchmarks/runs") / started_at.strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus = _read_jsonl(fixtures / "corpus.jsonl")
    questions = _read_jsonl(fixtures / "questions.jsonl")
    url_to_doc_key = _build_doc_key_index(corpus)

    pack = load_pack(settings.default_pack_id)
    resolved_domain = domain or pack.metadata.domain
    t2_model = _resolve_t2_model(pack, settings.t2_model)

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    embedder = Embedder(settings.t1_model)
    client = LLMClient(settings.llm_api_key, session_factory, base_url=settings.llm_base_url)

    try:
        if not skip_ingest:
            await _ingest_corpus(corpus, session_factory, embedder, settings.default_pack_id)
            await _extract_new_documents(corpus, session_factory, client, settings.default_pack_id)

        cross_doc_report = await classify_cross_document_relations(
            session_factory,
            client,
            domain=resolved_domain,
            pack=pack,
            model=t2_model,
        )

        async with session_factory() as session:
            await apply_lifecycle_transitions(session, domain=resolved_domain, pack=pack)
        async with session_factory() as session:
            await consolidate_domain(session, domain=resolved_domain, pack=pack)

        rows = await _answer_questions(
            questions, url_to_doc_key, session_factory, client, embedder, pack, k
        )
    finally:
        await engine.dispose()

    agg = aggregate(rows)
    finished_at = datetime.now(timezone.utc)

    _write_results(out_dir, rows)
    _write_report(out_dir, agg)
    _write_run_meta(
        out_dir,
        k=k,
        domain=resolved_domain,
        doc_count=len(corpus),
        question_count=len(questions),
        started_at=started_at,
        finished_at=finished_at,
        cross_doc_relations={
            "candidate_pairs": cross_doc_report.candidate_pairs,
            "classified_pairs": cross_doc_report.classified_pairs,
            "relations_created": cross_doc_report.relations_created,
            "skipped_existing": cross_doc_report.skipped_existing,
        },
    )

    return {"out_dir": str(out_dir), "aggregate": agg, "metric_keys": METRIC_KEYS}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Nexus memory benchmark.")
    parser.add_argument("--fixtures", type=Path, default=_DEFAULT_FIXTURES)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--domain", type=str, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    result = asyncio.run(
        run_benchmark(
            fixtures=args.fixtures,
            k=args.k,
            out=args.out,
            skip_ingest=args.skip_ingest,
            domain=args.domain,
        )
    )
    print(f"Wrote benchmark results to {result['out_dir']}")
    print(json.dumps(result["aggregate"]["overall"], indent=2))


if __name__ == "__main__":
    main()
