"""LongMemEval adapter: map haystack sessions to Nexus documents, run the full
memory pipeline per instance, and score with the benchmark QA-judge protocol.

Importable entry point: ``run_longmemeval`` (async). Does not require the FastAPI
server — builds its own session_factory from ``settings.database_url``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.routes_ingestion import (
    _chunk_and_embed,
    _get_or_create_manual_source,
    _persist_document,
)
from app.config import settings
from app.db.models import Document, SemanticCapsule, SemanticRelation
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
from app.intelligence.llm_client import LLMClient, LLMError, LLMNetworkError, LLMSchemaError

_DEFAULT_DATASET = Path("evals/memory/longmemeval/longmemeval_oracle.json")
_DEFAULT_CATEGORIES = ["knowledge-update", "temporal-reasoning"]
_SOURCE_NAME = "longmemeval"

# FK-safe order derived from app/db/models.py: children before parents;
# sources are kept so _get_or_create_manual_source reuses the same row per run.
_MEMORY_TABLES = (
    "capsule_segments",
    "semantic_relations",
    "theses",
    "semantic_capsules",
    "claim_evidence",
    "span_extractions",
    "claims",
    "spans",
    "documents",
)

_JUDGE_SYSTEM = (
    "You are a LongMemEval QA judge. Read the evaluation criteria and decide whether "
    "the model response is correct. Respond with JSON only: "
    '{"correct": true or false, "rationale": "brief explanation"}'
)


class LongMemEvalJudgeVerdict(BaseModel):
    correct: bool
    rationale: str


def render_session_text(turns: list[dict]) -> str:
    lines: list[str] = []
    for turn in turns:
        role = turn.get("role", "user")
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {turn.get('content', '')}")
    return "\n".join(lines)


def _parse_longmemeval_date(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    try:
        date_part = value.split(" (", maxsplit=1)[0]
        time_part = value.split(") ", maxsplit=1)[-1] if ") " in value else "00:00"
        parsed = datetime.strptime(f"{date_part} {time_part}", "%Y/%m/%d %H:%M")
        return parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def session_to_document(
    question_id: str,
    session_id: str,
    date: str | None,
    turns: list[dict],
    *,
    question_date: str | None = None,
    session_index: int = 0,
) -> dict[str, Any]:
    published_at = _parse_longmemeval_date(date)
    if published_at is None and question_date:
        published_at = _parse_longmemeval_date(question_date)
    return {
        "title": f"{question_id}/{session_index}",
        "url": f"longmemeval://{question_id}/{session_id}",
        "text": render_session_text(turns),
        "published_at": published_at,
    }


def select_instances(
    instances: list[dict],
    *,
    categories: list[str],
    limit: int,
    offset: int,
) -> list[dict]:
    filtered = [inst for inst in instances if inst.get("question_type") in categories]
    sliced = filtered[offset:]
    if limit > 0:
        sliced = sliced[:limit]
    return sliced


def shard_instances(
    instances: list[dict[str, Any]],
    *,
    workers: int,
    worker_index: int,
) -> list[tuple[int, dict[str, Any]]]:
    """Return (dataset_index, instance) pairs assigned to worker_index (1-based).

    Worker *i* receives instances[i-1::workers] — round-robin by original index.
    """
    return [
        (index, instance)
        for index, instance in enumerate(instances)
        if index % workers == worker_index - 1
    ]


def is_abstention(question_id: str) -> bool:
    return question_id.endswith("_abs")


def build_judge_prompt(
    question: str,
    gold_answer: str,
    hypothesis: str,
    *,
    abstention: bool,
    question_type: str = "knowledge-update",
) -> str:
    if abstention:
        template = (
            "I will give you an unanswerable question, an explanation, and a response from "
            "a model. Please answer yes if the model correctly identifies the question as "
            "unanswerable. The model could say that the information is incomplete, or some "
            "other information is given but the asked information is not.\n\n"
            "Question: {}\n\nExplanation: {}\n\nModel Response: {}\n\n"
            "Does the model correctly identify the question as unanswerable? Answer yes or no only."
        )
        return template.format(question, gold_answer, hypothesis)

    templates: dict[str, str] = {
        "single-session-user": (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
            "If the response is equivalent to the correct answer or contains all the intermediate "
            "steps to get the correct answer, you should also answer yes. If the response only "
            "contains a subset of the information required by the answer, answer no. "
            "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
            "Is the model response correct? Answer yes or no only."
        ),
        "single-session-assistant": (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
            "If the response is equivalent to the correct answer or contains all the intermediate "
            "steps to get the correct answer, you should also answer yes. If the response only "
            "contains a subset of the information required by the answer, answer no. "
            "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
            "Is the model response correct? Answer yes or no only."
        ),
        "multi-session": (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
            "If the response is equivalent to the correct answer or contains all the intermediate "
            "steps to get the correct answer, you should also answer yes. If the response only "
            "contains a subset of the information required by the answer, answer no. "
            "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
            "Is the model response correct? Answer yes or no only."
        ),
        "temporal-reasoning": (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
            "If the response is equivalent to the correct answer or contains all the intermediate "
            "steps to get the correct answer, you should also answer yes. If the response only "
            "contains a subset of the information required by the answer, answer no. In addition, "
            "do not penalize off-by-one errors for the number of days. If the question asks for the "
            "number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., "
            "predicting 19 days when the answer is 18), the model's response is still correct. "
            "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
            "Is the model response correct? Answer yes or no only."
        ),
        "knowledge-update": (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
            "If the response contains some previous information along with an updated answer, the "
            "response should be considered as correct as long as the updated answer is the required "
            "answer.\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
            "Is the model response correct? Answer yes or no only."
        ),
        "single-session-preference": (
            "I will give you a question, a rubric for desired personalized response, and a response "
            "from a model. Please answer yes if the response satisfies the desired response. "
            "Otherwise, answer no. The model does not need to reflect all the points in the rubric. "
            "The response is correct as long as it recalls and utilizes the user's personal "
            "information correctly.\n\nQuestion: {}\n\nRubric: {}\n\nModel Response: {}\n\n"
            "Is the model response correct? Answer yes or no only."
        ),
    }
    template = templates.get(question_type, templates["knowledge-update"])
    return template.format(question, gold_answer, hypothesis)


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _instance_to_corpus(instance: dict[str, Any]) -> list[dict[str, Any]]:
    question_id = instance["question_id"]
    question_date = instance.get("question_date")
    session_ids = instance.get("haystack_session_ids", [])
    dates = instance.get("haystack_dates", [])
    sessions = instance.get("haystack_sessions", [])
    corpus: list[dict[str, Any]] = []
    for idx, (session_id, turns) in enumerate(zip(session_ids, sessions, strict=False)):
        text = render_session_text(turns)
        if not text.strip():
            print(f"WARNING: skipping empty session {session_id} for {question_id}")
            continue
        date = dates[idx] if idx < len(dates) else None
        corpus.append(
            session_to_document(
                question_id,
                session_id,
                date,
                turns,
                question_date=question_date,
                session_index=idx,
            )
        )
    return corpus


def _git_rev() -> str:
    try:
        return subprocess.check_output(  # noqa: S603
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        ).strip()
    except Exception:  # noqa: BLE001 — best-effort only
        return "unknown"


async def _truncate_memory_tables(session_factory: async_sessionmaker) -> None:
    table_list = ", ".join(_MEMORY_TABLES)
    async with session_factory() as session:
        await session.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))
        await session.commit()


async def _ingest_corpus(
    corpus: list[dict[str, Any]],
    session_factory: async_sessionmaker,
    embedder: Any,
    domain_pack_id: str,
) -> tuple[int, int]:
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
                published_at=doc.get("published_at"),
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


async def _extract_documents(
    corpus: list[dict[str, Any]],
    session_factory: async_sessionmaker,
    client: LLMClient,
    *,
    t2_model: str,
) -> None:
    graph = make_extraction_graph(session_factory, client)
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Document.id, Document.status).where(
                    Document.url.in_([normalize_url(doc["url"]) for doc in corpus])
                )
            )
        ).all()
    for doc_id in [row.id for row in rows if row.status == "embedded"]:
        await run_with_context(graph, doc_id, t2_model)


async def _instance_stats(
    session_factory: async_sessionmaker,
    corpus_urls: list[str],
) -> tuple[int, int, int, list[str]]:
    async with session_factory() as session:
        doc_count = (
            await session.scalar(
                select(func.count()).select_from(Document).where(Document.url.in_(corpus_urls))
            )
            or 0
        )
        capsule_count = await session.scalar(select(func.count()).select_from(SemanticCapsule)) or 0
        relation_count = (
            await session.scalar(select(func.count()).select_from(SemanticRelation)) or 0
        )
        zero_capsule_rows = (
            await session.execute(
                select(Document.url)
                .outerjoin(SemanticCapsule, SemanticCapsule.document_id == Document.id)
                .where(Document.url.in_(corpus_urls))
                .group_by(Document.id)
                .having(func.count(SemanticCapsule.id) == 0)
            )
        ).all()
    zero_capsule_docs = [url for (url,) in zero_capsule_rows]
    return doc_count, capsule_count, relation_count, zero_capsule_docs


async def _judge_answer(
    client: LLMClient,
    *,
    question: str,
    gold_answer: str,
    hypothesis: str,
    question_type: str,
    abstention: bool,
) -> tuple[bool | None, int]:
    for _ in range(2):
        try:
            verdict, tokens = await client.complete_json(
                model=settings.t3_model,
                system=_JUDGE_SYSTEM,
                user=build_judge_prompt(
                    question,
                    gold_answer,
                    hypothesis,
                    abstention=abstention,
                    question_type=question_type,
                ),
                response_model=LongMemEvalJudgeVerdict,
                temperature=0.0,
                max_tokens=256,
                run_type="longmemeval_judge",
            )
            return verdict.correct, tokens
        except (LLMError, LLMNetworkError, LLMSchemaError):
            continue
    return None, 0


def _accuracy(rows: list[dict[str, Any]]) -> float | None:
    labels = [row["autoeval_label"] for row in rows if row.get("autoeval_label") is not None]
    if not labels:
        return None
    return sum(labels) / len(labels)


def _render_report(rows: list[dict[str, Any]], *, judge_model: str) -> str:
    overall_acc = _accuracy(rows)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_type.setdefault(row["question_type"], []).append(row)

    lines = [
        "# LongMemEval Report",
        "",
        "Oracle-retrieval framing: this run uses `longmemeval_oracle.json` evidence sessions "
        "only, measuring pipeline quality under oracle retrieval rather than full haystack recall.",
        "",
        f"Judge-model caveat: scores use `{judge_model}` (Nexus T3), not the paper's GPT-4o judge. "
        "Compare numbers cautiously; use `hypotheses.jsonl` with the official `evaluate_qa.py` "
        "for paper-comparable judging.",
        "",
        "## Overall",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| accuracy | {overall_acc:.3f} |" if overall_acc is not None else "| accuracy | n/a |",
    ]
    latencies = [row["latency_s"] for row in rows if row.get("latency_s") is not None]
    tokens = [row["tokens_used"] for row in rows if row.get("tokens_used") is not None]
    if latencies:
        lines.append(f"| mean_latency_s | {sum(latencies) / len(latencies):.3f} |")
    if tokens:
        lines.append(f"| mean_tokens_used | {sum(tokens) / len(tokens):.1f} |")
    lines.append("")

    for qtype, type_rows in sorted(by_type.items()):
        acc = _accuracy(type_rows)
        lines += [
            f"## {qtype}",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| n | {len(type_rows)} |",
            f"| accuracy | {acc:.3f} |" if acc is not None else "| accuracy | n/a |",
            "",
        ]
    return "\n".join(lines)


def _write_outputs(
    out_dir: Path,
    rows: list[dict[str, Any]],
    *,
    judge_model: str,
    run_meta: dict[str, Any],
) -> None:
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    with (out_dir / "hypotheses.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(
                json.dumps({"question_id": row["question_id"], "hypothesis": row["hypothesis"]})
                + "\n"
            )
    (out_dir / "report.md").write_text(
        _render_report(rows, judge_model=judge_model), encoding="utf-8"
    )
    (out_dir / "run_meta.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")


async def _run_single_instance(
    instance: dict[str, Any],
    *,
    session_factory: async_sessionmaker,
    embedder: Embedder,
    client: LLMClient,
    chat_graph: Any,
    pack_id: str,
    pack_obj: Any,
    resolved_domain: str,
    t2_model: str,
    k: int,
    append_partial: Callable[[dict[str, Any]], Any],
) -> tuple[dict[str, Any], int, int]:
    """Run the full per-instance pipeline. Returns (row, judge_errors, instance_errors)."""
    try:
        await _truncate_memory_tables(session_factory)
        corpus = _instance_to_corpus(instance)
        corpus_urls = [normalize_url(doc["url"]) for doc in corpus]

        await _ingest_corpus(corpus, session_factory, embedder, pack_id)
        await _extract_documents(corpus, session_factory, client, t2_model=t2_model)
        await classify_cross_document_relations(
            session_factory,
            client,
            domain=resolved_domain,
            pack=pack_obj,
            model=t2_model,
        )
        async with session_factory() as session:
            await apply_lifecycle_transitions(session, domain=resolved_domain, pack=pack_obj)
        async with session_factory() as session:
            await consolidate_domain(session, domain=resolved_domain, pack=pack_obj)

        doc_count, capsule_count, relation_count, zero_capsule_docs = await _instance_stats(
            session_factory, corpus_urls
        )

        start = time.monotonic()
        final = await run_chat_with_context(
            chat_graph,
            instance["question"],
            t2_model,
            top_k=k,
            pack=pack_obj,
            as_of=_parse_longmemeval_date(instance.get("question_date")),
        )
        latency_s = time.monotonic() - start

        hypothesis = final.get("answer") or INSUFFICIENT_EVIDENCE_ANSWER
        abstained = hypothesis == INSUFFICIENT_EVIDENCE_ANSWER
        abstention_q = is_abstention(instance["question_id"])

        autoeval_label, judge_tokens = await _judge_answer(
            client,
            question=instance["question"],
            gold_answer=instance["answer"],
            hypothesis=hypothesis,
            question_type=instance["question_type"],
            abstention=abstention_q,
        )
        judge_errors = 1 if autoeval_label is None else 0

        row = {
            "question_id": instance["question_id"],
            "question_type": instance["question_type"],
            "question": instance["question"],
            "gold_answer": instance["answer"],
            "hypothesis": hypothesis,
            "autoeval_label": autoeval_label,
            "abstained": abstained,
            "latency_s": latency_s,
            "tokens_used": final.get("tokens_used", 0),
            "judge_tokens_used": judge_tokens,
            "doc_count": doc_count,
            "capsule_count": capsule_count,
            "relation_count": relation_count,
            "zero_capsule_docs": zero_capsule_docs,
        }
        await append_partial(row)
        return row, judge_errors, 0
    except Exception as exc:  # noqa: BLE001 — one bad instance must not kill a worker
        print(f"ERROR instance {instance['question_id']}: {exc!r}")
        row = {
            "question_id": instance["question_id"],
            "question_type": instance["question_type"],
            "question": instance["question"],
            "gold_answer": instance["answer"],
            "hypothesis": None,
            "autoeval_label": None,
            "abstained": False,
            "error": repr(exc)[:300],
        }
        await append_partial(row)
        return row, 0, 1


async def _run_worker(
    worker_index: int,
    shard: list[tuple[int, dict[str, Any]]],
    *,
    db_url: str,
    embedder: Embedder,
    pack_id: str,
    pack_obj: Any,
    resolved_domain: str,
    t2_model: str,
    k: int,
    partial_lock: asyncio.Lock,
    partial_path: Path,
    engines: list[Any],
) -> tuple[list[tuple[int, dict[str, Any]]], int, int]:
    engine = make_engine(db_url)
    engines.append(engine)
    session_factory = make_session_factory(engine)
    client = LLMClient(settings.llm_api_key, session_factory, base_url=settings.llm_base_url)
    chat_graph = make_chat_graph(session_factory, client, embedder)

    async def append_partial(row: dict[str, Any]) -> None:
        async with partial_lock:
            with partial_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")

    indexed_rows: list[tuple[int, dict[str, Any]]] = []
    judge_errors = 0
    instance_errors = 0
    for dataset_index, instance in shard:
        row, judge_delta, instance_delta = await _run_single_instance(
            instance,
            session_factory=session_factory,
            embedder=embedder,
            client=client,
            chat_graph=chat_graph,
            pack_id=pack_id,
            pack_obj=pack_obj,
            resolved_domain=resolved_domain,
            t2_model=t2_model,
            k=k,
            append_partial=append_partial,
        )
        indexed_rows.append((dataset_index, row))
        judge_errors += judge_delta
        instance_errors += instance_delta
    return indexed_rows, judge_errors, instance_errors


async def run_longmemeval(
    *,
    dataset: Path = _DEFAULT_DATASET,
    categories: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    k: int = 5,
    out: Path | None = None,
    pack: str | None = None,
    workers: int = 1,
    db_url_template: str = "",
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    resolved_categories = categories or list(_DEFAULT_CATEGORIES)
    out_dir = (
        out or Path("docs/benchmarks/runs") / f"longmemeval-{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    instances = select_instances(
        _load_dataset(dataset),
        categories=resolved_categories,
        limit=limit,
        offset=offset,
    )

    if workers > 1 and "{n}" not in db_url_template:
        msg = "--db-url-template must contain '{n}' when --workers > 1"
        raise ValueError(msg)

    pack_id = pack or settings.default_pack_id
    pack_obj = load_pack(pack_id)
    resolved_domain = pack_obj.metadata.domain
    t2_model = _resolve_t2_model(pack_obj, settings.t2_model)

    embedder = Embedder(settings.t1_model)
    judge_errors = 0
    instance_errors = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    partial_path = out_dir / "results.partial.jsonl"
    engines: list[Any] = []

    try:
        if workers == 1:
            engine = make_engine(settings.database_url)
            engines.append(engine)
            session_factory = make_session_factory(engine)
            client = LLMClient(
                settings.llm_api_key, session_factory, base_url=settings.llm_base_url
            )
            chat_graph = make_chat_graph(session_factory, client, embedder)

            async def append_partial(row: dict[str, Any]) -> None:
                # A killed multi-hour run must not lose completed instances.
                with partial_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")

            indexed_rows: list[tuple[int, dict[str, Any]]] = []
            for dataset_index, instance in enumerate(instances):
                row, judge_delta, instance_delta = await _run_single_instance(
                    instance,
                    session_factory=session_factory,
                    embedder=embedder,
                    client=client,
                    chat_graph=chat_graph,
                    pack_id=pack_id,
                    pack_obj=pack_obj,
                    resolved_domain=resolved_domain,
                    t2_model=t2_model,
                    k=k,
                    append_partial=append_partial,
                )
                indexed_rows.append((dataset_index, row))
                judge_errors += judge_delta
                instance_errors += instance_delta
        else:
            partial_lock = asyncio.Lock()
            worker_results = await asyncio.gather(
                *[
                    _run_worker(
                        worker_index,
                        shard_instances(instances, workers=workers, worker_index=worker_index),
                        db_url=db_url_template.format(n=worker_index),
                        embedder=embedder,
                        pack_id=pack_id,
                        pack_obj=pack_obj,
                        resolved_domain=resolved_domain,
                        t2_model=t2_model,
                        k=k,
                        partial_lock=partial_lock,
                        partial_path=partial_path,
                        engines=engines,
                    )
                    for worker_index in range(1, workers + 1)
                ]
            )
            indexed_rows = []
            for worker_indexed_rows, worker_judge_errors, worker_instance_errors in worker_results:
                indexed_rows.extend(worker_indexed_rows)
                judge_errors += worker_judge_errors
                instance_errors += worker_instance_errors

        indexed_rows.sort(key=lambda item: item[0])
        rows = [row for _, row in indexed_rows]
    finally:
        for engine in engines:
            await engine.dispose()

    finished_at = datetime.now(timezone.utc)
    run_meta: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "git_rev": _git_rev(),
        "dataset": str(dataset),
        "categories": resolved_categories,
        "limit": limit,
        "offset": offset,
        "k": k,
        "workers": workers,
        "t1_model": settings.t1_model,
        "t2_model": t2_model,
        "t3_model": settings.t3_model,
        "judge_model": settings.t3_model,
        "llm_base_url": settings.llm_base_url,
        "instance_count": len(instances),
        "judge_errors": judge_errors,
        "instance_errors": instance_errors,
        "domain": resolved_domain,
        "pack_id": pack_id,
    }
    if workers > 1:
        run_meta["db_url_template"] = db_url_template
    _write_outputs(out_dir, rows, judge_model=settings.t3_model, run_meta=run_meta)

    return {
        "out_dir": str(out_dir),
        "accuracy": _accuracy(rows),
        "instance_count": len(rows),
        "judge_errors": judge_errors,
        "instance_errors": instance_errors,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LongMemEval memory adapter.")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument(
        "--categories",
        type=str,
        default=",".join(_DEFAULT_CATEGORIES),
        help="Comma-separated question_type values to include.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Max instances (0 = no limit).")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--pack",
        type=str,
        default=None,
        help="Domain pack id (defaults to settings.default_pack_id).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel worker count (1 = sequential, today's default).",
    )
    parser.add_argument(
        "--db-url-template",
        type=str,
        default="",
        help="Per-worker DB URL template with {n} placeholder (required when --workers > 1).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    result = asyncio.run(
        run_longmemeval(
            dataset=args.dataset,
            categories=categories,
            limit=args.limit,
            offset=args.offset,
            k=args.k,
            out=args.out,
            pack=args.pack,
            workers=args.workers,
            db_url_template=args.db_url_template,
        )
    )
    print(f"Wrote LongMemEval results to {result['out_dir']}")
    if result["accuracy"] is not None:
        print(f"Accuracy: {result['accuracy']:.3f}")


if __name__ == "__main__":
    main()
