# Plan: LongMemEval Adapter + Evaluation (H7)

**Spec:** `docs/superpowers/specs/2026-07-03-longmemeval-adapter.md`
**Branch:** `claude/longmemeval-h7` (worktree `.worktree/longmemeval`)

One delegated implementation task; orchestrator downloads the dataset and runs the live
evaluation (needs credentials + scratch DB).

## File structure

- `scripts/benchmarks/run_longmemeval.py` — NEW. Pure helpers + async pipeline +
  argparse `__main__` (mirrors `run_memory_benchmark.py`'s shape).
- `tests/benchmarks/test_longmemeval_adapter.py` — NEW. Pure-helper unit tests only
  (no DB, no LLM).
- `evals/memory/longmemeval/README.md` — NEW. Download + usage instructions.
- `.gitignore` — add `evals/memory/longmemeval/*.json`.

## Task decomposition

### T-L1 — Adapter script + unit tests (delegated)

**Consumes** (all existing, import-only, none may be edited):
- `app.api.routes_ingestion._get_or_create_manual_source`, `._persist_document`,
  `._chunk_and_embed` — study how `run_memory_benchmark._ingest_corpus` uses them and
  mirror that usage (including `normalize_url`/`content_hash` handling and doc status
  flow).
- `app.intelligence.extraction.make_extraction_graph`, `.run_with_context`,
  `._resolve_t2_model`
- `app.intelligence.cross_relations.classify_cross_document_relations`
- `app.intelligence.lifecycle.apply_lifecycle_transitions`
- `app.intelligence.consolidation.consolidate_domain`
- `app.intelligence.chat.make_chat_graph`, `.run_chat_with_context`,
  `.INSUFFICIENT_EVIDENCE_ANSWER`
- `app.intelligence.llm_client.LLMClient` (+ `settings.llm_api_key/llm_base_url/t3_model`)
- `app.intelligence.embedder.Embedder`, `app.db.session.make_engine/make_session_factory`

**Produces** (per the spec's Data model section, exact signatures):
- Pure helpers `render_session_text`, `session_to_document`, `select_instances`,
  `is_abstention`, `build_judge_prompt`, `LongMemEvalJudgeVerdict`.
- `async def run_longmemeval(*, dataset: Path, categories: list[str], limit: int,
  offset: int, k: int, out: Path | None) -> dict` — per-instance: truncate memory
  tables (`TRUNCATE ... CASCADE` on capsule_segments, semantic_relations, theses,
  semantic_capsules, span/document-layer tables — verify exact table list against
  `app/db/models.py` and truncate in dependency-safe order; keep `sources` or recreate
  per run, implementer's choice, documented) → ingest sessions as documents → extract →
  cross-doc relations → lifecycle → consolidate → answer → judge (T3, one call,
  `run_type="longmemeval_judge"`) → write outputs per spec Requirement 5.
- Argparse `__main__` with the spec's flags.
- Unit tests for every pure helper including `--offset` slicing determinism and the
  `_abs` judge-prompt branch.

**Boundaries:** NO git operations. No edits to any existing module (new files +
`.gitignore` line only). Full-suite self-check (`ruff check`, `ruff format --check`,
`mypy app/`, `pytest` with
`DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_lme_t`); 6 known
pre-existing failures; single trailing newline per file. The adapter script must not
import from `run_memory_benchmark.py` (keep the two runners independent; shared-helper
extraction is a logged follow-up, not this task).

### T-L2 — Dataset download + live evaluation (orchestrator, not delegated)

`huggingface-cli download xiaowu0162/longmemeval-cleaned` (oracle file) into
`evals/memory/longmemeval/`; fresh scratch DB `nexus_lme`; run the default subset
(knowledge-update + temporal-reasoning, limit 20); inspect per-instance capsule counts
for the pack-mismatch risk before trusting accuracy; write
`docs/benchmarks/longmemeval-baseline-2026-07-03.md` from the run artifacts.

## T-L5 — answer-path temporal grounding + conflict resolution (spec amendment 2026-07-04)

Three delegated sub-tasks, sequential (T-L5a and T-L5b both touch
`app/intelligence/prompts/chat_answer.py`).

### T-L5a — question-time anchor + dated context blocks (delegated)

**Consumes:** `Document.published_at` (exists, populated by adapter ingestion);
chat state dict in `app/intelligence/chat.py`; `_parse_longmemeval_date` in the adapter.

**Produces:**
- `run_chat_with_context(graph, question, model, *, top_k, pack=None, as_of: datetime | None = None) -> dict`
  — `as_of` defaults to `datetime.now(timezone.utc)` inside, stored in chat state.
- `build_user_prompt(question, context_blocks, *, hint="", as_of: datetime | None = None) -> str`
  — renders `Current date: YYYY-MM-DD (Weekday)` before the question; per-block
  `Date: YYYY-MM-DD (Weekday)` line when the block has `published_at`.
- Both capsule queries (hybrid candidates + `_fetch_capsules_by_ids`) select
  `Document.published_at`; `_build_context_block` copies it to the block dict.
- Adapter (`run_longmemeval.py`): pass `as_of=_parse_longmemeval_date(question_date)`.
- Unit tests: prompt rendering with/without dates (pure, no DB).

**Boundaries:** no git ops; no changes to classifier, router, extraction, schema.
Existing callers must keep working without passing `as_of`.

### T-L5b — conflict-resolution prompt + multi_doc recall (delegated)

**Consumes:** T-L5a's landed `chat_answer.py`.
**Produces:** `SYSTEM_PROMPT` conflict-resolution instruction (resolve via
supersession/lifecycle/dates, single answer, never "conflicting evidence");
`router.py` `multi_doc`: `top_k_delta=5`, hint extended with enumerate-and-count
guidance. No signature changes.

### T-L5c — judge retry (delegated)

**Consumes:** `_judge_answer` in `run_longmemeval.py`.
**Produces:** one retry on `LLMError`/`LLMNetworkError`/`LLMSchemaError` before
returning `(None, 0)`. No signature change.

## Build order

T-L1 → orchestrator full gate + commit → T-L2 → report commit → Submit PR flow.
T-L5: wait for full-211 baseline run to finish (it is the "before" number) →
T-L5a → gate + commit → T-L5b → gate + commit → T-L5c → gate + commit → rerun 211
(T-L5d, orchestrator) → before/after report → Submit PR flow.

## Risks

- **Pack-domain mismatch** (spec: top risk) — T-L2 explicitly checks capsules-per-doc
  before reading accuracy; zero-capsule evidence sessions mean the number measures the
  pack, not the architecture.
- **Truncation order** — FK violations if the table order is wrong; the implementer must
  derive order from `app/db/models.py` FKs, and a dry unit test can't cover it — T-L2's
  live run is the check.
- **Judge leniency drift** — Qwen T3 judge vs paper's GPT-4o; mitigated by also emitting
  `hypotheses.jsonl` for external re-judging with the official script.
