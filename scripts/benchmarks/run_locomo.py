"""LoCoMo adapter: ingest each conversation's sessions once, then answer every one of
that conversation's QA pairs against the shared ingested state, scoring with an
LLM-judge protocol analogous to the LongMemEval adapter's.

Importable entry point: ``run_locomo`` (async). Does not require the FastAPI server —
builds its own session_factory from ``settings.database_url`` (or ``--db-url``).

Key design difference vs LongMemEval (see ``run_longmemeval.py``): LongMemEval is one
haystack per question, so that adapter truncates + re-ingests per question. LoCoMo is
~10 conversations each carrying many QA pairs, so this adapter ingests once per
conversation and shards across workers by conversation, not by question. Several
pipeline-generic helpers (DB truncation, ingestion, extraction, corpus stats, git rev,
accuracy aggregation, conversation sharding, context-block serialization) are reused by
import from ``run_longmemeval`` rather than duplicated, per the project's reuse
convention -- they carry no LongMemEval-specific assumptions. Turn rendering, document
construction, category handling, and the judge prompt are LoCoMo-specific and are
implemented fresh here (LoCoMo turns use ``speaker``/``text`` keys and numeric
``category`` codes, not LongMemEval's ``role``/``content`` and ``question_type`` string).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import `app`/`scripts` from this script's own tree, not the venv's editable
# install — otherwise a worktree run silently benchmarks the main checkout's code.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
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
from app.intelligence.extraction import _resolve_t2_model
from app.intelligence.lifecycle import apply_lifecycle_transitions
from app.intelligence.llm_client import LLMClient, LLMError, LLMNetworkError, LLMSchemaError
from app.intelligence.sentence_window import answer_sentence_window
from scripts.benchmarks.run_longmemeval import (
    _accuracy,
    _extract_documents,
    _git_rev,
    _ingest_corpus,
    _ingest_sentence_window_corpus,
    _instance_stats,
    _resolve_k,
    _serialize_blocks,
    _truncate_memory_tables,
    shard_instances,
)

_DEFAULT_DATASET = Path("evals/memory/locomo/locomo10.json")
_SOURCE_NAME = "locomo"

# Category numbers per the official LoCoMo eval code (task_eval/{evaluation,gpt_utils}.py
# in https://github.com/snap-research/locomo): category 2 gets a "use date of
# conversation" hint (temporal) and category 5 is scored via an unanswerable/adversarial
# check -- both confirmed directly in the upstream source. Categories 1 and 3/4 are not
# distinguished by any code branch there; this mapping follows the ordering the task
# brief itself used (multi-hop, temporal, open-domain, single-hop, adversarial) and is
# used only for report labeling, not scoring logic.
_CATEGORY_NAMES: dict[int, str] = {
    1: "multi_hop",
    2: "temporal",
    3: "open_domain",
    4: "single_hop",
    5: "adversarial",
}
_DEFAULT_CATEGORIES = sorted(_CATEGORY_NAMES)

# Experiment harness: when True, _run_single_conversation serializes the retrieved
# context_blocks into each row so results.jsonl doubles as a replay cache for
# answer-path A/B (scripts/benchmarks/replay_answer.py). Off in normal runs.
_DUMP_CONTEXT = False

_JUDGE_SYSTEM = (
    "You are a LoCoMo QA judge. Read the evaluation criteria and decide whether "
    "the model response is correct. Respond with JSON only: "
    '{"correct": true or false, "rationale": "brief explanation"}'
)


class LoCoMoJudgeVerdict(BaseModel):
    correct: bool
    rationale: str


def category_name(category: int | None) -> str:
    if category is None:
        return "unknown"
    return _CATEGORY_NAMES.get(category, f"category_{category}")


def is_adversarial(category: int | None) -> bool:
    return category == 5


def render_locomo_session_text(turns: list[dict[str, Any]]) -> str:
    return "\n".join(f"{turn.get('speaker', 'Unknown')}: {turn.get('text', '')}" for turn in turns)


def _parse_locomo_datetime(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    try:
        return datetime.strptime(value, "%I:%M %p on %d %B, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def conversation_sessions(
    conversation: dict[str, Any],
) -> list[tuple[int, str | None, list[dict[str, Any]]]]:
    """Ordered (session_number, date_time, turns) triples for populated sessions.

    Some locomo10.json samples pad extra ``session_N_date_time`` keys beyond the last
    populated session (verified: e.g. sample conv-26 carries date_time keys up to 35
    while turn content stops at 19) -- anchor iteration on the numeric suffixes of the
    ``session_N`` (content) keys, not the date_time keys.
    """
    session_numbers = sorted(
        int(key.split("_")[1])
        for key in conversation
        if key.startswith("session_") and not key.endswith("_date_time")
    )
    return [
        (n, conversation.get(f"session_{n}_date_time"), conversation[f"session_{n}"])
        for n in session_numbers
    ]


def session_to_document(
    sample_id: str,
    session_number: int,
    date_time: str | None,
    turns: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "title": f"{sample_id}/session_{session_number}",
        "url": f"locomo://{sample_id}/session_{session_number}",
        "text": render_locomo_session_text(turns),
        "published_at": _parse_locomo_datetime(date_time),
    }


def _conversation_to_corpus(sample: dict[str, Any]) -> list[dict[str, Any]]:
    sample_id = sample["sample_id"]
    corpus: list[dict[str, Any]] = []
    for session_number, date_time, turns in conversation_sessions(sample["conversation"]):
        text = render_locomo_session_text(turns)
        if not text.strip():
            print(f"WARNING: skipping empty session {session_number} for {sample_id}")
            continue
        corpus.append(session_to_document(sample_id, session_number, date_time, turns))
    return corpus


def _last_session_as_of(conversation: dict[str, Any]) -> datetime | None:
    """Anchor for the chat's "current date": LoCoMo has no per-question timestamp (unlike
    LongMemEval's question_date), so use the latest ingested session's date -- the point
    at which the full conversation history is available -- as the temporal "now".
    """
    parsed = [
        d
        for _, date_time, _ in conversation_sessions(conversation)
        if (d := _parse_locomo_datetime(date_time)) is not None
    ]
    return max(parsed) if parsed else None


def select_conversations(
    samples: list[dict[str, Any]], *, limit: int, offset: int
) -> list[dict[str, Any]]:
    sliced = samples[offset:]
    if limit > 0:
        sliced = sliced[:limit]
    return sliced


def select_questions(
    qa_list: list[dict[str, Any]], *, categories: list[int], limit: int
) -> list[dict[str, Any]]:
    filtered = [qa for qa in qa_list if qa.get("category") in categories]
    if limit > 0:
        filtered = filtered[:limit]
    return filtered


def gold_answer_text(qa: dict[str, Any]) -> str:
    """The gradeable "gold" text: adversarial (category 5) items carry no correct answer
    in the dataset, only ``adversarial_answer`` -- a plausible-sounding wrong answer used
    to check the model doesn't confabulate it. Correct behavior there is abstention.
    """
    if is_adversarial(qa.get("category")):
        return str(qa.get("adversarial_answer", ""))
    return str(qa.get("answer"))


def build_judge_prompt(
    question: str,
    gold_answer: str,
    hypothesis: str,
    *,
    category: int | None,
) -> str:
    if is_adversarial(category):
        return (
            "I will give you a question that has no answer in the conversation, a "
            "plausible-sounding but incorrect answer a naive model might give, and a "
            "response from a model being evaluated. Please answer yes if the model "
            "correctly identifies the question as unanswerable from the conversation "
            "(e.g. says the information is not mentioned or not available). Answer no "
            "if the model instead gives the plausible-but-incorrect answer or any other "
            "confident answer.\n\nQuestion: {}\n\nPlausible but incorrect answer: {}\n\n"
            "Model Response: {}\n\nDoes the model correctly identify the question as "
            "unanswerable? Answer yes or no only."
        ).format(question, gold_answer, hypothesis)

    if category == 2:  # temporal
        return (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Approximate "
            "dates/durations are acceptable; do not penalize off-by-one-day errors or "
            "reasonable rounding. Otherwise, answer no.\n\nQuestion: {}\n\nCorrect Answer: "
            "{}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no "
            "only."
        ).format(question, gold_answer, hypothesis)

    return (
        "I will give you a question, a correct answer, and a response from a model. "
        "Please answer yes if the response contains the correct answer or is equivalent "
        "to it. If the response only contains a subset of the required information, "
        "answer no.\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
        "Is the model response correct? Answer yes or no only."
    ).format(question, gold_answer, hypothesis)


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


async def _judge_answer(
    client: LLMClient,
    *,
    question: str,
    gold_answer: str,
    hypothesis: str,
    category: int | None,
) -> tuple[bool | None, int]:
    # complete_json already retries 429/5xx/network internally; only LLMSchemaError
    # goes unretried there, so that's the one case worth a second attempt here.
    for attempt in range(2):
        try:
            verdict, tokens = await client.complete_json(
                model=settings.t3_model,
                system=_JUDGE_SYSTEM,
                user=build_judge_prompt(question, gold_answer, hypothesis, category=category),
                response_model=LoCoMoJudgeVerdict,
                temperature=0.0,
                max_tokens=256,
                run_type="locomo_judge",
            )
            return verdict.correct, tokens
        except LLMSchemaError:
            if attempt == 0:
                continue
            return None, 0
        except (LLMError, LLMNetworkError):
            return None, 0
    return None, 0


def _render_report(rows: list[dict[str, Any]], *, judge_model: str) -> str:
    overall_acc = _accuracy(rows)
    by_category: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        by_category.setdefault(row.get("category"), []).append(row)

    lines = [
        "# LoCoMo Report",
        "",
        "Full-conversation framing: each conversation's sessions are ingested once "
        "through the full pipeline (ingest -> extract -> cross-doc relations -> "
        "lifecycle -> consolidate); every selected question for that conversation is "
        "then answered against the same ingested state -- no per-question "
        "re-ingestion, unlike the LongMemEval adapter.",
        "",
        f"Judge-model caveat: scores use `{judge_model}` (Nexus T3) via an LLM-judge "
        "yes/no protocol, not the official LoCoMo repo's F1/ROUGE/exact-match scripts. "
        "Numbers are not directly comparable to published LoCoMo leaderboard results.",
        "",
        "Category legend: 1=multi_hop, 2=temporal, 3=open_domain, 4=single_hop, "
        "5=adversarial (correct behavior is abstention; see run_locomo.py header "
        "comment for the mapping's provenance).",
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

    for category, cat_rows in sorted(
        by_category.items(), key=lambda item: (item[0] is None, item[0])
    ):
        acc = _accuracy(cat_rows)
        lines += [
            f"## {category} ({category_name(category)})",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| n | {len(cat_rows)} |",
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


async def _run_single_conversation(
    sample: dict[str, Any],
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
    mode: str,
    categories: list[int],
    question_limit: int,
    append_partial: Any,
) -> tuple[list[dict[str, Any]], int, int]:
    """Ingest one conversation's sessions once, then answer every selected question
    against that shared state. Returns (rows, judge_errors, question_errors).
    """
    sample_id = sample["sample_id"]
    try:
        await _truncate_memory_tables(session_factory)
        corpus = _conversation_to_corpus(sample)
        corpus_urls = [normalize_url(doc["url"]) for doc in corpus]

        sentence_span_count = 0
        if mode == "sentence-window":
            doc_count, _skipped, sentence_span_count = await _ingest_sentence_window_corpus(
                corpus, session_factory, embedder, pack_id
            )
            capsule_count = 0
            relation_count = 0
            zero_capsule_docs = []
        else:
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
        as_of = _last_session_as_of(sample["conversation"])
    except Exception as exc:  # noqa: BLE001 — one bad conversation must not kill a worker
        print(f"ERROR conversation {sample_id}: {exc!r}")
        row = {
            "question_id": f"{sample_id}/ingest",
            "sample_id": sample_id,
            "category": None,
            "question": None,
            "gold_answer": None,
            "hypothesis": None,
            "autoeval_label": None,
            "abstained": False,
            "error": repr(exc)[:300],
        }
        await append_partial(row)
        return [row], 0, 1

    qa_list = select_questions(sample["qa"], categories=categories, limit=question_limit)
    rows: list[dict[str, Any]] = []
    judge_errors = 0
    question_errors = 0
    for qa_index, qa in enumerate(qa_list):
        question_id = f"{sample_id}/{qa_index}"
        try:
            category = qa.get("category")
            gold_answer = gold_answer_text(qa)

            start = time.monotonic()
            if mode == "sentence-window":
                final = await answer_sentence_window(
                    session_factory,
                    client,
                    embedder,
                    qa["question"],
                    t2_model,
                    fetch_k=settings.sentence_window_fetch_k,
                    window=settings.sentence_window_size,
                    k=k,
                    as_of=as_of,
                    pack=pack_obj,
                )
            else:
                final = await run_chat_with_context(
                    chat_graph,
                    qa["question"],
                    t2_model,
                    top_k=k,
                    pack=pack_obj,
                    as_of=as_of,
                )
            latency_s = time.monotonic() - start

            hypothesis = final.get("answer") or INSUFFICIENT_EVIDENCE_ANSWER
            abstained = hypothesis == INSUFFICIENT_EVIDENCE_ANSWER

            autoeval_label, judge_tokens = await _judge_answer(
                client,
                question=qa["question"],
                gold_answer=gold_answer,
                hypothesis=hypothesis,
                category=category,
            )
            if autoeval_label is None:
                judge_errors += 1

            row = {
                "question_id": question_id,
                "sample_id": sample_id,
                "category": category,
                "category_name": category_name(category),
                "question": qa["question"],
                "gold_answer": gold_answer,
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
                "sentence_span_count": sentence_span_count,
            }
            if _DUMP_CONTEXT:
                row["as_of"] = as_of.isoformat() if as_of else None
                row["question_shape"] = final.get("question_shape")
                row["context_blocks"] = _serialize_blocks(final.get("context_blocks", []))
            rows.append(row)
            await append_partial(row)
        except Exception as exc:  # noqa: BLE001 — one bad question must not lose the rest
            print(f"ERROR question {question_id}: {exc!r}")
            row = {
                "question_id": question_id,
                "sample_id": sample_id,
                "category": qa.get("category"),
                "question": qa.get("question"),
                "gold_answer": None,
                "hypothesis": None,
                "autoeval_label": None,
                "abstained": False,
                "error": repr(exc)[:300],
            }
            rows.append(row)
            await append_partial(row)
            question_errors += 1
    return rows, judge_errors, question_errors


async def _run_worker(
    worker_index: int,
    shard: list[tuple[int, dict[str, Any]]],
    *,
    db_url: str,
    pack_id: str,
    pack_obj: Any,
    resolved_domain: str,
    t2_model: str,
    k: int,
    mode: str,
    categories: list[int],
    question_limit: int,
    partial_lock: asyncio.Lock,
    partial_path: Path,
    engines: list[Any],
) -> tuple[list[tuple[int, int, dict[str, Any]]], int, int]:
    engine = make_engine(db_url)
    engines.append(engine)
    session_factory = make_session_factory(engine)
    # Each worker gets its own Embedder: SentenceTransformer.encode() is a blocking
    # synchronous call with no internal await point, so a shared instance would
    # serialize every worker's embedding calls behind whichever one is mid-encode.
    embedder = Embedder(settings.t1_model)
    client = LLMClient(settings.llm_api_key, session_factory, base_url=settings.llm_base_url)
    chat_graph = make_chat_graph(session_factory, client, embedder)

    async def append_partial(row: dict[str, Any]) -> None:
        async with partial_lock:
            with partial_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")

    indexed_rows: list[tuple[int, int, dict[str, Any]]] = []
    judge_errors = 0
    question_errors = 0
    for conv_index, sample in shard:
        rows, judge_delta, question_delta = await _run_single_conversation(
            sample,
            session_factory=session_factory,
            embedder=embedder,
            client=client,
            chat_graph=chat_graph,
            pack_id=pack_id,
            pack_obj=pack_obj,
            resolved_domain=resolved_domain,
            t2_model=t2_model,
            k=k,
            mode=mode,
            categories=categories,
            question_limit=question_limit,
            append_partial=append_partial,
        )
        for qa_index, row in enumerate(rows):
            indexed_rows.append((conv_index, qa_index, row))
        judge_errors += judge_delta
        question_errors += question_delta
    return indexed_rows, judge_errors, question_errors


async def run_locomo(
    *,
    dataset: Path = _DEFAULT_DATASET,
    categories: list[int] | None = None,
    limit: int = 0,
    offset: int = 0,
    question_limit: int = 0,
    k: int | None = None,
    out: Path | None = None,
    pack: str | None = None,
    workers: int = 1,
    db_url_template: str = "",
    db_url: str | None = None,
    mode: str = "semantic",
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    resolved_categories = categories or list(_DEFAULT_CATEGORIES)
    out_dir = (
        out or Path("docs/benchmarks/runs") / f"locomo-{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = select_conversations(_load_dataset(dataset), limit=limit, offset=offset)

    if workers > 1 and "{n}" not in db_url_template:
        msg = "--db-url-template must contain '{n}' when --workers > 1"
        raise ValueError(msg)

    pack_id = pack or settings.default_pack_id
    pack_obj = load_pack(pack_id)
    resolved_domain = pack_obj.metadata.domain
    t2_model = _resolve_t2_model(pack_obj, settings.t2_model)
    resolved_k = _resolve_k(mode, k)

    judge_errors = 0
    question_errors = 0
    partial_path = out_dir / "results.partial.jsonl"
    engines: list[Any] = []
    rows: list[dict[str, Any]] = []

    try:
        if workers == 1:
            embedder = Embedder(settings.t1_model)
            # Unlike run_longmemeval's --workers 1 path (which always uses
            # settings.database_url), --db-url lets a single-worker LoCoMo run target a
            # scratch DB explicitly without relying on .env — the LongMemEval adapter's
            # documented footgun (see docs/superpowers/specs, "Environment facts").
            engine = make_engine(db_url or settings.database_url)
            engines.append(engine)
            session_factory = make_session_factory(engine)
            client = LLMClient(
                settings.llm_api_key, session_factory, base_url=settings.llm_base_url
            )
            chat_graph = make_chat_graph(session_factory, client, embedder)

            async def append_partial(row: dict[str, Any]) -> None:
                # A killed multi-hour run must not lose completed questions.
                with partial_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")

            indexed_rows: list[tuple[int, int, dict[str, Any]]] = []
            for conv_index, sample in enumerate(samples):
                conv_rows, judge_delta, question_delta = await _run_single_conversation(
                    sample,
                    session_factory=session_factory,
                    embedder=embedder,
                    client=client,
                    chat_graph=chat_graph,
                    pack_id=pack_id,
                    pack_obj=pack_obj,
                    resolved_domain=resolved_domain,
                    t2_model=t2_model,
                    k=resolved_k,
                    mode=mode,
                    categories=resolved_categories,
                    question_limit=question_limit,
                    append_partial=append_partial,
                )
                for qa_index, row in enumerate(conv_rows):
                    indexed_rows.append((conv_index, qa_index, row))
                judge_errors += judge_delta
                question_errors += question_delta
        else:
            partial_lock = asyncio.Lock()
            worker_results = await asyncio.gather(
                *[
                    _run_worker(
                        worker_index,
                        shard_instances(samples, workers=workers, worker_index=worker_index),
                        db_url=db_url_template.format(n=worker_index),
                        pack_id=pack_id,
                        pack_obj=pack_obj,
                        resolved_domain=resolved_domain,
                        t2_model=t2_model,
                        k=resolved_k,
                        mode=mode,
                        categories=resolved_categories,
                        question_limit=question_limit,
                        partial_lock=partial_lock,
                        partial_path=partial_path,
                        engines=engines,
                    )
                    for worker_index in range(1, workers + 1)
                ]
            )
            indexed_rows = []
            for worker_indexed_rows, worker_judge_errors, worker_question_errors in worker_results:
                indexed_rows.extend(worker_indexed_rows)
                judge_errors += worker_judge_errors
                question_errors += worker_question_errors

        indexed_rows.sort(key=lambda item: (item[0], item[1]))
        rows = [row for _, _, row in indexed_rows]
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
        "question_limit": question_limit,
        "k": resolved_k,
        "mode": mode,
        "workers": workers,
        "t1_model": settings.t1_model,
        "t2_model": t2_model,
        "t3_model": settings.t3_model,
        "judge_model": settings.t3_model,
        "llm_base_url": settings.llm_base_url,
        "conversation_count": len(samples),
        "question_count": len(rows),
        "judge_errors": judge_errors,
        "question_errors": question_errors,
        "domain": resolved_domain,
        "pack_id": pack_id,
    }
    if workers > 1:
        run_meta["db_url_template"] = db_url_template
    _write_outputs(out_dir, rows, judge_model=settings.t3_model, run_meta=run_meta)

    return {
        "out_dir": str(out_dir),
        "accuracy": _accuracy(rows),
        "conversation_count": len(samples),
        "question_count": len(rows),
        "judge_errors": judge_errors,
        "question_errors": question_errors,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LoCoMo memory adapter.")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument(
        "--categories",
        type=str,
        default=",".join(str(c) for c in _DEFAULT_CATEGORIES),
        help=(
            "Comma-separated category ints to include "
            "(1=multi_hop, 2=temporal, 3=open_domain, 4=single_hop, 5=adversarial)."
        ),
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Max conversations after offset (0 = no limit)."
    )
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument(
        "--question-limit",
        type=int,
        default=0,
        help="Max questions per conversation after category filter (0 = no limit).",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=None,
        help="Retrieval top-k (semantic default 5; sentence-window default from settings).",
    )
    parser.add_argument(
        "--mode",
        choices=("semantic", "sentence-window"),
        default="semantic",
        help="Ingest+answer path: semantic pipeline (default) or sentence-window retrieval.",
    )
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
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="DB URL for --workers 1 (defaults to settings.database_url from .env if omitted).",
    )
    parser.add_argument(
        "--dump-context",
        action="store_true",
        help="Serialize retrieved context_blocks into results.jsonl for answer-path replay.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    global _DUMP_CONTEXT
    args = _parse_args(argv)
    _DUMP_CONTEXT = args.dump_context
    categories = [int(c.strip()) for c in args.categories.split(",") if c.strip()]
    result = asyncio.run(
        run_locomo(
            dataset=args.dataset,
            categories=categories,
            limit=args.limit,
            offset=args.offset,
            question_limit=args.question_limit,
            k=args.k,
            out=args.out,
            pack=args.pack,
            workers=args.workers,
            db_url_template=args.db_url_template,
            db_url=args.db_url,
            mode=args.mode,
        )
    )
    print(f"Wrote LoCoMo results to {result['out_dir']}")
    if result["accuracy"] is not None:
        print(f"Accuracy: {result['accuracy']:.3f}")


if __name__ == "__main__":
    main()
