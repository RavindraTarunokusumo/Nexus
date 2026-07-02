# Plan — Phases D, E, F (Qwen Hackathon critical path)

Date: 2026-07-02. Branch: `claude/def-hackathon`. Deadline: 2026-07-09 5pm EDT.

Spec basis: TODO.md Phase D/E/F items (hackathon-scoped, minimal versions explicitly
sanctioned there). Per user instruction this session skips the interactive
spec-acceptance step; this plan is the implementer contract.

Verified environment facts (2026-07-02):

- Qwen Cloud OpenAI-compatible base URL: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
  (domestic endpoint rejects the account key). `qwen3.6-flash` and `qwen3.7-max` both
  respond live with the `QWEN_CLOUD_API_KEY` in `.env`.
- Working Postgres: `postgresql+asyncpg://nexus:nexus@localhost:5434/nexus` (pgvector, migrated).
- Baseline on clean main @ 154430a: 14 pre-existing pytest failures (6 = known
  `capsule_segments.role="support"` CHECK violation, 6 = `test_extraction_graph`,
  1 = `test_loader` path traversal, 1 = `test_chat_api` 503), 2 ruff errors, 3 mypy
  errors. Implementers must not chase or "fix" these.

## Task graph (maximal parallelization)

Wave 1 — six tasks, disjoint file scopes, all parallel, same worktree, no git ops:

| Task | TODO items | Writes (exclusive) |
|------|-----------|--------------------|
| T-D12 | D1, D2 | `app/intelligence/chat.py`, `app/intelligence/prompts/chat_answer.py`, `tests/test_chat_context_assembly.py` (new), existing chat tests if signatures require |
| T-D3 | D3 | `app/config.py`, `app/intelligence/llm_client.py`, `app/api/deps.py` (and any other `LLMClient(` constructor site), `.env.example` (new), `tests/test_llm_client_config.py` (new) |
| T-E12 | E1, E2 | `app/intelligence/lifecycle.py` (new), `app/cli/lifecycle.py` (new), `tests/intelligence/test_lifecycle.py` (new) |
| T-E3 | E3 | `app/intelligence/consolidation.py` (new), `app/cli/consolidation.py` (new), `tests/intelligence/test_consolidation.py` (new) |
| T-F2 | F2 | `evals/memory/nexus_synthetic/` (new: corpus.jsonl, questions.jsonl, README.md) |
| T-F1 | F1 | `docs/benchmarks/memory-benchmark-plan.md` (new) |

Wave 1.5 — orchestrator only: register `lifecycle_app` / `consolidation_app` typers in
`app/cli/main.py` (only file with cross-task contention; reserved to orchestrator).

Wave 2 — two tasks, parallel (depend on Wave 1 landing for imports/fixtures):

| Task | TODO items | Writes (exclusive) |
|------|-----------|--------------------|
| T-F35 | F3, F5 | `scripts/benchmarks/run_memory_benchmark.py` (new), `scripts/benchmarks/scoring.py` (new), `tests/benchmarks/test_scoring.py` (new) |
| T-F4 | F4 | `app/cli/eval.py` (append `eval memory` subcommands only) |

Wave 3 — orchestrator only: F6 live baseline run (ingest fixtures → extract → lifecycle
→ consolidate → benchmark with Qwen) + `docs/benchmarks/baseline-template.md` + first
baseline report + docs/TODO updates + PR.

Runtime (not code-time) dependencies: benchmark supersession/thesis questions only score
well after E1–E3 run against the ingested corpus; that ordering lives in the runner
pipeline and Wave 3 execution, not in code structure.

## Interfaces (cross-task contract)

### T-D12 — context assembly + un-stubbed hybrid scoring

Consumes: `pack.retrieval_policy.hybrid_score_weights`, `pack.context_assembly`
(`include`, `ordering`, `max_tokens_by_tier`), `SemanticCapsule.epistemic_state` (JSONB:
`source_authority`, `evidence_quality` — values per `app/intelligence/llm_client.py`
EpistemicState literals), `SemanticRelation`.

Produces:

- `compute_hybrid_score(candidate, weights, retrieval_priorities, recency_min, recency_max) -> float`
  (same signature) where `candidate` gains keys `epistemic_state: dict` and
  `relation_count: int`. Deterministic mappings:
  - source_authority: primary 1.0, secondary 0.66, tertiary 0.33, unknown/missing 0.5.
  - evidence_quality: high 1.0, medium 0.6, low 0.3, unknown/missing 0.5.
  - relation_relevance: `min(1.0, relation_count / 4)`.
- Retrieval query in `_run_retrieve_capsules` adds `epistemic_state` column and a
  per-capsule relation count (relations where the capsule is source or target).
- Primary retrieval lifecycle filter widens from `== "active"` to
  `IN ("active", "confirmed", "qualified")`.
- Context assembly honoring `pack.context_assembly.include` categories after top-k
  selection: each context block gains `role` key —
  `"primary"` (highest_salience_relevant_objects),
  `"counter_evidence"` (capsules linked to a selected block via relations with
  polarity "negative" or relation_type "contradicts"),
  `"supersession"` (capsules linked via relation_type "supersedes", either direction,
  found regardless of lifecycle_state, annotated superseding vs superseded);
  `source_refs_and_excerpts` = existing evidence spans; `epistemic_notes` = new
  `epistemic_note: str` on each block summarizing authority/status/evidence_quality/
  lifecycle. Categories absent from `include` are skipped. Auxiliary blocks get labels
  continuing the `C{i}` sequence, count toward neither top_k nor budget beyond a hard
  cap of 2 counter-evidence + 2 supersession blocks per answer.
- `ordering: evidence_strength`: final block order sorts by
  `0.5*evidence_quality_score + 0.3*authority_score + 0.2*capsule_confidence`
  (primary blocks first, then auxiliary). Any other `ordering` value keeps score order.
- `build_user_prompt` renders role + epistemic note per block; system prompt updated to
  explain counter-evidence/supersession blocks (cite them when relevant; prefer
  superseding facts over superseded ones).
- `ChatCitation` gains `role: str | None` and `epistemic_note: str | None`.

### T-D3 — Qwen T2+ wiring

Produces:

- `app/config.py` Settings gains: `llm_base_url: str = "https://openrouter.ai/api/v1"`,
  `qwen_cloud_api_key: str = ""`, `embedding_model: str = "BAAI/bge-small-en-v1.5"`
  (env already sets EMBEDDING_MODEL; must not crash startup), and property
  `llm_api_key -> str` returning `qwen_cloud_api_key or openrouter_api_key`.
  Default t2/t3 models stay as-is in code; env overrides them (already qwen names).
- `LLMClient.__init__(api_key, session_factory, base_url: str = <openrouter>)`; module
  `_BASE_URL` stays the default. All constructor sites pass
  `settings.llm_api_key` + `settings.llm_base_url`.
- `.env.example` (new) documenting DATABASE_URL, REDIS_URL, QWEN_CLOUD_API_KEY,
  LLM_BASE_URL (dashscope-intl compatible-mode URL), T1/T2/T3_MODEL with Qwen names,
  APP_SECRET.
- Does NOT touch `.env` (orchestrator adds LLM_BASE_URL there).

### T-E12 — lifecycle worker (E1) + stale/supersession detection (E2)

Produces `app/intelligence/lifecycle.py`:

- `LifecycleTransition` (pydantic): capsule_id, from_state, to_state, reason.
- `LifecycleReport` (pydantic): domain, transitions: list[LifecycleTransition],
  counts: dict[str, int].
- `async def apply_lifecycle_transitions(session, *, domain: str, pack: DomainPack, now: datetime | None = None, dry_run: bool = False) -> LifecycleReport`

Deterministic rules, in precedence order (first match wins per capsule; only capsules
currently in `candidate` or `active` transition; never resurrect terminal states;
allowed states per migration 0005 `_LIFECYCLE_STATES`):

1. superseded — incoming relation `relation_type == "supersedes"` (capsule is target);
   OR supersession_rules heuristic when `pack.retention_policy.supersession_rules`
   non-empty: another capsule in same domain with same `domain_object_type`, same
   primary actor facet (first of facets key "orgs" or "people", case-insensitive),
   and strictly newer `created_at` ⇒ older capsule superseded.
2. contradicted — incoming/outgoing relation `relation_type == "contradicts"` where the
   other side has strictly higher authority rank (primary > secondary > tertiary > unknown).
3. qualified — incoming relation `relation_type == "qualifies"`.
4. confirmed — ≥2 distinct supporting relations (`relation_type` in
   ("supports", "confirms") or polarity "positive", strength ≥ 0.6).
5. stale — only when `pack.retention_policy.stale_conditions` non-empty:
   `domain_object_type == "forecast"` and `created_at` older than
   `warm_window_days`; or any capsule older than `cold_after_days`.
6. archived — `retention_policy.archive_after_days` set and capsule older ⇒ archived.

Updates `lifecycle_state` + `updated_at`; commit unless dry_run (then rollback).

`app/cli/lifecycle.py`: typer app `lifecycle_app`, command `run` with `--domain`,
`--pack`, `--dry-run`, `--json` following `app/cli/theses.py` conventions (use
`_run()`-equivalent event-loop-safe helper, NOT bare `asyncio.run` — see TODO "CLI
asyncio.run() footgun"; a local `_run` copy matching `app/cli/main.py::_run` is
acceptable to avoid circular imports). Do NOT edit `app/cli/main.py`.

### T-E3 — consolidation worker (E3)

Produces `app/intelligence/consolidation.py`:

- `ConsolidationReport` (pydantic): domain, theses_created: int, thesis_ids: list[UUID],
  skipped_existing: int (0 if unknown).
- `async def consolidate_domain(session, *, domain: str, pack: DomainPack, min_strength: float = 0.6, min_cluster_size: int = 2, created_by_tier: str = "t3", dry_run: bool = False) -> ConsolidationReport`
  — thin orchestration over `app.intelligence.theses.synthesize_theses_from_relations`
  (Phase C writer owns clustering/dedup; this module owns the worker entry point and
  report shape).

`app/cli/consolidation.py`: typer app `consolidation_app`, command `run`, same CLI
conventions as T-E12. Do NOT edit `app/cli/main.py`.

### T-F2 — synthetic memory fixtures

`evals/memory/nexus_synthetic/corpus.jsonl` — one doc/line:
`{"doc_key": str, "title": str, "url": str (unique fake https URL), "source_type": str (one of pack supported_source_types), "published_at": ISO8601, "text": str (300–900 words, dense factual AI-tech content)}`

Corpus: 12–16 docs forming a coherent fictional-but-realistic AI-tech timeline
(model releases with versions/dates, benchmark results across ≥2 docs, a pricing
change superseding an earlier price, a deprecated model, a rumor (tertiary) conflicting
with an official statement (primary), an expired forecast, ≥3 docs supporting one
investable thesis). Facts must be internally consistent and dated 2025-09..2026-06.

`questions.jsonl` — one/line:
`{"question_id": str, "category": "timeline"|"multi_doc"|"superseded"|"authority_conflict"|"thesis"|"abstention", "question": str, "expected_answer_keywords": [str] (lowercase), "forbidden_keywords": [str] (lowercase, may be empty), "expected_doc_keys": [str], "expected_abstain": bool, "notes": str}`

≥3 questions per category (≥18 total). Abstention questions ask about facts absent
from the corpus; their expected_doc_keys=[] and expected_abstain=true.
`README.md` documents schema + categories. No Python code.

### T-F35 — benchmark runner + metrics

`scripts/benchmarks/scoring.py` (importable, pure):

- `score_answer(question: dict, answer: str, cited_doc_keys: list[str], retrieved_doc_keys: list[str], abstained: bool) -> dict` returning per-question metric dict:
  - answer_correctness — fraction of expected_answer_keywords in answer (lowercased); 1.0 for correct abstention.
  - forbidden_violation — any forbidden_keyword present (bool).
  - evidence_recall_at_k — |cited ∩ expected_doc_keys| / |expected_doc_keys| (None when expected empty).
  - citation_precision — |cited ∩ expected| / |cited| (None when no citations).
  - citation_faithfulness — cited ⊆ retrieved (bool).
  - temporal_correctness — for category timeline: answer_correctness AND no forbidden_violation (else None).
  - supersession_correctness — for category superseded: correct keywords present AND no forbidden (superseded-fact) keywords (else None).
  - abstention_accuracy — abstained == expected_abstain (bool).
- `aggregate(rows: list[dict]) -> dict` — per-category and overall means, plus latency
  p50/p95 and total token cost fields when present in rows.

`scripts/benchmarks/run_memory_benchmark.py` — asyncio CLI (argparse or typer),
flags `--fixtures DIR --k INT --out DIR --skip-ingest --domain`. Pipeline:

1. Ingest corpus.jsonl docs that aren't already present (idempotent by URL) using the
   text-ingestion path (see `app/api/routes_ingestion.py` / `nexus ingest text`) with
   chunk+embed, then run the extraction graph per document
   (`app.intelligence.extraction`, T2 model from settings).
2. Run `apply_lifecycle_transitions` then `consolidate_domain`.
3. For each question: build chat graph (`make_chat_graph`) with real `LLMClient`
   (settings-driven Qwen) + embedder, call `run_chat_with_context`, record wall latency,
   `tokens_used`, answer, citations; abstained = answer == INSUFFICIENT_EVIDENCE_ANSWER.
   Map cited document URLs back to doc_keys via corpus URL index.
4. Score with `scoring.py`; write `results.jsonl`, `report.md` (aggregate table
   per category + overall, F5 metric names), `run_meta.json` (models, k, git rev,
   timestamps) under `--out`.

Self-check test `tests/benchmarks/test_scoring.py` covers scoring edge cases (empty
citations, abstention, forbidden hit). Runner itself is NOT unit-tested (exercised live
in Wave 3).

### T-F4 — eval CLI surface

Appends to `app/cli/eval.py`:

- `nexus eval memory run --benchmark nexus_synthetic --k N [--out DIR] [--skip-ingest]`
  — subprocess-free: imports and invokes the runner's async entry function.
- `nexus eval memory report --run-id <id>` — prints `report.md` (and summary line) from
  `docs/benchmarks/runs/<run-id>/`.
- Benchmark name maps to `evals/memory/<name>/`; run-id = out-dir basename (timestamp).

## Build order

1. Wave 1 (parallel ×6) → orchestrator: normalize, full-suite gate, commit per task.
2. Wave 1.5 CLI registration commit.
3. Wave 2 (parallel ×2) → same gate, commit per task.
4. Wave 3 live baseline (F6) + docs + PR.

## Risks

- Concurrent implementer self-checks share one Postgres → each Grok subagent gets its
  own database (`nexus_t1`..`nexus_t6`) via DATABASE_URL to keep full-suite self-checks
  honest without cross-talk.
- `qwen3.6-flash`/`qwen3.7-max` return `reasoning_content` alongside `content`;
  `complete_json` reads only `content` — verified OK live, but empty-`content`
  edge (all budget spent on reasoning) may need `max_tokens` headroom in Wave 3 runs.
- D2 widens the retrieval lifecycle filter — existing chat tests asserting the `active`
  filter may need updating (in T-D12's exclusive scope).
- 14 pre-existing test failures must not be "fixed" by implementers (scope creep guard).
