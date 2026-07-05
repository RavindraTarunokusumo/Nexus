"""Answer-path replay lab for LongMemEval.

Reads a results.jsonl produced with `run_longmemeval.py --dump-context` (each row
carries the serialized retrieved `context_blocks`, `as_of`, `gold_answer`, etc.),
then re-runs ONLY the answer LLM + judge under one or more variant configs.

Because the capsules are held fixed, this isolates the answer path (model,
thinking-mode, block ordering, prompt/hint) from extraction stochasticity and
skips the expensive ingest+extract entirely — the token-efficient way to search
the answer-path design space.

Usage:
    python -m scripts.benchmarks.replay_answer --cache <results.jsonl> \
        --variants baseline chrono think think_chrono t3 t3_chrono
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.config import settings
from app.db.session import make_engine, make_session_factory
from app.intelligence.chat import ChatAnswerOutput
from app.intelligence.llm_client import LLMClient, LLMError, LLMNetworkError
from app.intelligence.prompts.chat_answer import SYSTEM_PROMPT, build_user_prompt
from app.intelligence.router import resolve_strategy
from scripts.benchmarks.run_longmemeval import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    _judge_answer,
    is_abstention,
)


class ChatAnswerCoN(BaseModel):
    notes: str = ""
    answer: str
    citations: list[str] = []


# Chain-of-Note: an in-band reasoning field (cheap alternative to thinking-mode)
# that folds in the concrete LongMemEval failure fixes — resolve each event's
# absolute date, sort for ordering, compute deltas explicitly, enumerate for
# counting, and abstain on entity-mismatch distractors.
COT_SYSTEM = (
    SYSTEM_PROMPT.replace(
        "Return JSON with keys: answer, citations.",
        "Return JSON with keys: notes, answer, citations.",
    )
    + "\n\nBefore answering, use the 'notes' field to reason briefly and concretely:\n"
    "1. List each relevant context block with its resolved absolute date — combine the "
    "block 'Date:' line with any relative phrase in the excerpt (e.g. 'two weeks ago' "
    "relative to that block's date).\n"
    "2. Ordering ('which happened first / most recent'): sort those events by date and "
    "name the first/latest.\n"
    "3. Duration / elapsed time ('how long', 'how many days/weeks/months ago/between'): "
    "state the two anchor dates and compute the difference explicitly.\n"
    "4. Counting ('how many'): enumerate every distinct matching occurrence across all "
    "blocks, then count.\n"
    "5. If the question's subject (person, place, activity, or role) does not exactly "
    "match one in the evidence — e.g. it asks about 'table tennis' when only 'tennis' "
    "appears, or 'Dr. Johnson' when only 'Dr. Smith' appears — do NOT answer from the "
    "near match; abstain with the insufficient-evidence sentence.\n"
    "Keep 'notes' short. Put only the final user-facing response in 'answer'."
)
# Fail fast if chat_answer.py's schema sentence changed and the .replace() above
# silently no-op'd — otherwise every cot* variant would run the wrong schema.
if "notes, answer, citations" not in COT_SYSTEM:
    raise RuntimeError("SYSTEM_PROMPT schema sentence changed; update COT_SYSTEM's replace target.")


@dataclass(frozen=True)
class Variant:
    name: str
    model: str = "t2"  # "t2" | "t3"
    thinking: bool = False
    order: str = "score"  # "score" | "chrono"
    use_hint: bool = True
    cot: bool = False  # Chain-of-Note in-band reasoning field
    max_blocks: int = 0  # 0 = all; else keep top-N by retrieval score (token trim)
    lean_prompt: bool = False  # strip per-block metadata noise (keeps all blocks)
    system: str | None = None  # None -> default (SYSTEM_PROMPT or COT_SYSTEM)


VARIANTS: dict[str, Variant] = {
    "baseline": Variant("baseline"),
    "chrono": Variant("chrono", order="chrono"),
    "cot": Variant("cot", cot=True),
    "cot_chrono": Variant("cot_chrono", cot=True, order="chrono"),
    "think": Variant("think", thinking=True),
    "think_chrono": Variant("think_chrono", thinking=True, order="chrono"),
    "t3": Variant("t3", model="t3"),
    "t3_chrono": Variant("t3_chrono", model="t3", order="chrono"),
    "t3_cot_chrono": Variant("t3_cot_chrono", model="t3", cot=True, order="chrono"),
    "think_cot_chrono": Variant("think_cot_chrono", thinking=True, cot=True, order="chrono"),
    # sweep 2: combine the two best levers (CoN + strong/thinking model), score order.
    "t3_cot": Variant("t3_cot", model="t3", cot=True),
    "think_cot": Variant("think_cot", thinking=True, cot=True),
    "t3_think_cot": Variant("t3_think_cot", model="t3", thinking=True, cot=True),
    # token-efficiency path: CoN reasoning on the fast model with a trimmed context.
    "cot_chrono_lean6": Variant("cot_chrono_lean6", cot=True, order="chrono", max_blocks=6),
    "cot_chrono_lean8": Variant("cot_chrono_lean8", cot=True, order="chrono", max_blocks=8),
    "lean6": Variant("lean6", max_blocks=6),
    # efficiency path: lean per-block prompt (all blocks kept) + CoN on fast model.
    "leanprompt": Variant("leanprompt", lean_prompt=True),
    "cot_leanprompt": Variant("cot_leanprompt", cot=True, lean_prompt=True),
    "t3_leanprompt": Variant("t3_leanprompt", model="t3", lean_prompt=True),
}


def _build_lean_prompt(
    question: str,
    context_blocks: list[dict[str, Any]],
    *,
    hint: str,
    as_of: datetime | None,
) -> str:
    # Token-lean block format: prompt tokens dominate (~85% of total) and most
    # per-block lines (URL, Title, Object type, Score, Epistemic note) are noise
    # the answer model ignores. Keep label, Date, Role, capsule text, 1 excerpt —
    # preserving every evidence block (no starvation) at a fraction of the tokens.
    blocks = []
    for b in context_blocks:
        lines = [f"[{b['label']}]"]
        pub = b.get("published_at")
        if pub is not None:
            lines.append(f"Date: {pub.strftime('%Y-%m-%d (%a)')}")
        if b.get("role"):
            lines.append(f"Role: {b['role']}")
        lines.append(b["text"])
        evidence = b.get("evidence") or []
        if evidence and evidence[0].get("text"):
            lines.append(f"Excerpt: {evidence[0]['text']}")
        blocks.append("\n".join(lines))
    parts: list[str] = []
    if as_of is not None:
        parts.append(f"Current date: {as_of.strftime('%Y-%m-%d (%a)')}")
    parts.extend(["Question:", question, "Context:", "\n\n".join(blocks)])
    if hint:
        parts.append(f"Answer guidance: {hint}")
    return "\n\n".join(parts)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _prep_blocks(
    raw_blocks: list[dict[str, Any]], order: str, max_blocks: int = 0
) -> list[dict[str, Any]]:
    blocks = [dict(b) for b in raw_blocks]
    for b in blocks:
        b["published_at"] = _parse_dt(b.get("published_at"))
    if max_blocks and len(blocks) > max_blocks:
        # keep the highest-scoring blocks (retrieval order), then (re)order below
        blocks = sorted(blocks, key=lambda b: b.get("score", 0.0), reverse=True)[:max_blocks]
    if order == "chrono":
        # Undated blocks sort last; stable within equal dates preserves retrieval rank.
        blocks.sort(key=lambda b: (b["published_at"] is None, b["published_at"] or datetime.min))
    return blocks


async def _answer_one(
    client: LLMClient, variant: Variant, row: dict[str, Any], sem: asyncio.Semaphore
) -> dict[str, Any]:
    async with sem:
        raw_blocks = row.get("context_blocks") or []
        model = settings.t3_model if variant.model == "t3" else settings.t2_model
        shape = row.get("question_shape") or "general"
        hint = resolve_strategy(shape).answer_hint if variant.use_hint else ""

        if not raw_blocks:
            hypothesis = INSUFFICIENT_EVIDENCE_ANSWER
            tokens = 0
        else:
            blocks = _prep_blocks(raw_blocks, variant.order, variant.max_blocks)
            build = _build_lean_prompt if variant.lean_prompt else build_user_prompt
            user = build(row["question"], blocks, hint=hint, as_of=_parse_dt(row.get("as_of")))
            system = variant.system or (COT_SYSTEM if variant.cot else SYSTEM_PROMPT)
            model_cls = ChatAnswerCoN if variant.cot else ChatAnswerOutput
            try:
                result, tokens = await client.complete_json(
                    model=model,
                    system=system,
                    user=user,
                    response_model=model_cls,
                    run_type="chat_answer",
                    thinking=variant.thinking,
                    max_tokens=6000 if variant.thinking else 2000,
                )
                hypothesis = result.answer or INSUFFICIENT_EVIDENCE_ANSWER
            except (LLMError, LLMNetworkError) as exc:
                hypothesis = INSUFFICIENT_EVIDENCE_ANSWER
                tokens = 0
                print(f"  answer error {row['question_id']}: {exc!r}"[:160])

        abstained = hypothesis == INSUFFICIENT_EVIDENCE_ANSWER
        label, judge_tokens = await _judge_answer(
            client,
            question=row["question"],
            gold_answer=row["gold_answer"],
            hypothesis=hypothesis,
            question_type=row["question_type"],
            abstention=is_abstention(row["question_id"]),
        )
        return {
            "question_id": row["question_id"],
            "question_type": row["question_type"],
            "autoeval_label": label,
            "abstained": abstained,
            "tokens_used": tokens,
            "hypothesis": hypothesis,
        }


def _summarize(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [r for r in rows if r["autoeval_label"] is not None]
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in labeled:
        by_type[r["question_type"]].append(r)
    acc = sum(r["autoeval_label"] for r in labeled) / len(labeled) if labeled else 0.0
    mean_tok = sum(r["tokens_used"] for r in rows) / len(rows) if rows else 0.0
    per_type = {
        t: round(sum(r["autoeval_label"] for r in rs) / len(rs), 3) for t, rs in by_type.items()
    }
    return {
        "variant": name,
        "n": len(rows),
        "labeled": len(labeled),
        "accuracy": round(acc, 3),
        "mean_tokens": round(mean_tok, 1),
        "abstain": sum(r["abstained"] for r in rows),
        "per_type": per_type,
    }


async def _run_variant(
    client: LLMClient, variant: Variant, cache: list[dict[str, Any]], concurrency: int
) -> dict[str, Any]:
    sem = asyncio.Semaphore(concurrency)
    # return_exceptions: one malformed row or unexpected error must not abort a
    # whole variant mid-sweep. Errored rows get autoeval_label=None (excluded from
    # accuracy, same as a judge error) and are counted in the summary.
    settled = await asyncio.gather(
        *[_answer_one(client, variant, r, sem) for r in cache], return_exceptions=True
    )
    rows: list[dict[str, Any]] = []
    errors = 0
    for src, res in zip(cache, settled, strict=True):
        if isinstance(res, Exception):
            errors += 1
            print(f"  row error {src.get('question_id', '?')}: {res!r}"[:160])
            rows.append(
                {
                    "question_id": src.get("question_id", "?"),
                    "question_type": src.get("question_type", "?"),
                    "autoeval_label": None,
                    "abstained": False,
                    "tokens_used": 0,
                    "hypothesis": "",
                }
            )
        else:
            rows.append(res)
    summary = _summarize(variant.name, rows)
    summary["errors"] = errors
    return {"summary": summary, "rows": rows}


async def main_async(args: argparse.Namespace, cache: list[dict[str, Any]]) -> None:
    print(f"Loaded {len(cache)} cached instances from {args.cache}")

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    client = LLMClient(settings.llm_api_key, session_factory, base_url=settings.llm_base_url)

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    try:
        for vname in args.variants:
            variant = VARIANTS[vname]
            print(
                f"\n=== variant: {vname} (model={variant.model} think={variant.thinking} "
                f"order={variant.order}) ==="
            )
            res = await _run_variant(client, variant, cache, args.concurrency)
            summaries.append(res["summary"])
            print(json.dumps(res["summary"], indent=2))
            if out_dir:
                (out_dir / f"{vname}.jsonl").write_text(
                    "\n".join(json.dumps(r) for r in res["rows"]) + "\n"
                )
    finally:
        await engine.dispose()

    print("\n===== COMPARISON =====")
    print(f"{'variant':18s} {'acc':>6s} {'tok':>7s} {'abst':>5s}  per_type")
    for s in summaries:
        print(
            f"{s['variant']:18s} {s['accuracy']:>6.3f} {s['mean_tokens']:>7.0f} "
            f"{s['abstain']:>5d}  {s['per_type']}"
        )
    if out_dir:
        (out_dir / "comparison.json").write_text(json.dumps(summaries, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay LongMemEval answer path under variants.")
    parser.add_argument("--cache", required=True, help="results.jsonl with context_blocks.")
    parser.add_argument("--variants", nargs="+", default=["baseline"], choices=list(VARIANTS))
    parser.add_argument("--limit", type=int, default=0, help="Cap instances (0 = all).")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()
    raw = [json.loads(line) for line in Path(args.cache).read_text().splitlines() if line.strip()]
    # Only rows carrying a "context_blocks" key came from a --dump-context run;
    # error-path rows omit it, and a plain benchmark results.jsonl has none at all.
    # Skipping keyless rows avoids scoring failed instances as no-evidence
    # abstentions and turns "wrong file" into a loud error, not silent 0.0 accuracy.
    cache = [r for r in raw if "context_blocks" in r]
    skipped = len(raw) - len(cache)
    if not cache:
        raise SystemExit(
            f"{args.cache}: no rows contain 'context_blocks' — rebuild the cache with "
            "`run_longmemeval.py --dump-context`."
        )
    if skipped:
        print(f"Skipped {skipped} row(s) without context_blocks (instance errors / non-dump).")
    if args.limit:
        cache = cache[: args.limit]
    asyncio.run(main_async(args, cache))


if __name__ == "__main__":
    main()
