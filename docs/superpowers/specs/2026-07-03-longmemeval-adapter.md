# Spec: LongMemEval Adapter + Evaluation (H7)

**Date:** 2026-07-03
**Status:** Accepted (hackathon fast-path)
**TODO ref:** H7 — external benchmark run for empirical demonstration (top priority).

## Problem

The synthetic `nexus_synthetic` benchmark proves the pipeline works but carries no
external credibility. LongMemEval (ICLR 2025, 500 instances) is a recognized long-term
memory benchmark with published comparison numbers, and two of its six categories —
`knowledge-update` and `temporal-reasoning` — map directly onto Nexus's supersession and
timeline capabilities. Nexus needs an adapter that runs LongMemEval instances through the
real ingest → extract → cross-doc relations → lifecycle → consolidate → answer pipeline
and scores them with the benchmark's own QA-judge protocol.

## Dataset facts (verified)

- Files: `longmemeval_oracle.json` (evidence sessions only), `longmemeval_s.json`
  (~40 sessions / ~115k tokens per instance), `longmemeval_m.json` (~500 sessions).
  HuggingFace: `xiaowu0162/longmemeval-cleaned` (plain JSON list).
- Instance fields: `question_id` (suffix `_abs` marks abstention questions),
  `question_type` (6 categories), `question`, `answer`, `question_date`,
  `haystack_session_ids`, `haystack_dates` (parallel list), `haystack_sessions`
  (list of sessions; each session is a list of `{"role", "content"}` turns, evidence
  turns carry `"has_answer": true`), `answer_session_ids`.
- Official eval: LLM judge over (question, gold answer, hypothesis) → `autoeval_label`;
  the paper uses GPT-4o. Output contract for their `evaluate_qa.py`: JSONL rows with
  `question_id` + `hypothesis`.

## Requirements

1. **Adapter** `scripts/benchmarks/run_longmemeval.py`: for each selected instance,
   map each haystack session to one Nexus document (turns rendered as
   `User: …` / `Assistant: …` lines; session date → `Document.published_at`; synthetic
   URL `longmemeval://{question_id}/{session_id}`; title from question_id + index), then
   run the full pipeline (ingest+embed → extraction graph per doc → cross-doc relation
   pass → lifecycle → consolidation) and answer `question` through the chat graph
   (`run_chat_with_context`, router active).
2. **Instance isolation**: every instance has an independent history. Truncate the
   memory tables (documents/spans/capsules/relations/theses/segments — cascade-safe
   order) between instances on the scratch DB. No cross-instance contamination.
3. **Selection controls**: `--dataset <path>` (default `evals/memory/longmemeval/longmemeval_oracle.json`),
   `--categories <comma-list>` (default `knowledge-update,temporal-reasoning`),
   `--limit N` (default 20, `0` = no limit), `--offset N` (resume), `--k` (top_k,
   default 5), `--out <dir>`.
4. **Scoring**: implement the LongMemEval QA-judge protocol with the T3 model
   (`qwen3.7-max`): judge prompt takes question, gold answer, hypothesis → yes/no
   correctness (`autoeval_label`). Abstention questions (`question_id` ends `_abs`):
   correct iff the hypothesis abstains/declines. Report accuracy overall and per
   `question_type`, plus mean latency and token usage. The judge-model difference vs
   the paper's GPT-4o must be stated in the report as a comparability caveat.
5. **Outputs** under `--out`: `results.jsonl` (one row per instance: `question_id`,
   `question_type`, `question`, `gold_answer`, `hypothesis`, `autoeval_label`,
   `abstained`, latency, tokens, per-instance doc/capsule/relation counts),
   `hypotheses.jsonl` (`question_id` + `hypothesis` only — directly consumable by the
   official `evaluate_qa.py`), `report.md`, `run_meta.json` (dataset file, categories,
   limit/offset, models, git rev).
6. **Dataset not committed**: `evals/memory/longmemeval/README.md` documents the
   `huggingface-cli download` step and the adapter usage; `.gitignore` covers
   `evals/memory/longmemeval/*.json`.

## Non-goals (v1)

- No `longmemeval_s`/`_m` full-haystack runs (extraction cost; oracle-first measures
  pipeline quality under oracle retrieval — state this framing in the report).
- No session-level recall metrics from `answer_session_ids`/`has_answer` (logged as
  follow-up; requires citation→session mapping).
- No new domain pack: run with `settings.default_pack_id`. **Known risk** (see below).

## Data model

No DB schema changes. New pure helpers (unit-testable without DB/LLM):

```python
def render_session_text(turns: list[dict]) -> str            # role-labelled transcript
def session_to_document(question_id, session_id, date, turns) -> dict  # url/title/text/published_at
def select_instances(instances, *, categories, limit, offset) -> list[dict]
def is_abstention(question_id: str) -> bool
class LongMemEvalJudgeVerdict(BaseModel): correct: bool; rationale: str
def build_judge_prompt(question, gold_answer, hypothesis, *, abstention: bool) -> str
```

Async pipeline reuses existing app internals exactly as `run_memory_benchmark.py` does
(`_persist_document`/`_chunk_and_embed`-equivalent ingestion, `make_extraction_graph` +
`run_with_context`, `classify_cross_document_relations`, `apply_lifecycle_transitions`,
`consolidate_domain`, `make_chat_graph` + `run_chat_with_context`).

## Edge cases

- Session with no parseable date → fall back to `question_date`, else omit
  `published_at` (adapter must not crash).
- Empty/whitespace-only session → skip that session, log it.
- Judge LLM error → `autoeval_label: null`, excluded from accuracy mean, counted in
  `judge_errors` in run_meta.
- Extraction producing zero capsules for an instance (transient LLM failure) → record
  `zero_capsule_docs` per instance in results row; the answer still runs (likely
  abstains).
- `--offset`/`--limit` slice AFTER category filtering, deterministic dataset order.

## Success criteria

1. Full suite green (6 pre-existing failures only); new pure helpers unit-tested
   (session rendering, selection/offset, abstention detection, judge prompt).
2. Live run: default subset (knowledge-update + temporal-reasoning, `--limit 20`,
   oracle file) completes end-to-end on Qwen Cloud with a written report showing
   per-category accuracy — whatever the numbers are, reported honestly with the
   oracle-retrieval framing and judge-model caveat.
3. `hypotheses.jsonl` validates against the official script's input contract
   (`question_id` + `hypothesis` per line).

## Constraints / known risks

- **Pack-domain mismatch (top risk)**: the `personal_ai_tech` pack's telos/salience is
  tuned for AI-tech news, while LongMemEval sessions are personal-assistant chat.
  Extraction may under-extract personal facts. v1 accepts this and reports it; if the
  live run shows evidence sessions yielding zero relevant capsules, a minimal
  `longmemeval_v1` pack is the documented follow-up, not an in-scope fix.
  **Amendment (T-L2 run 1, confirmed):** 0/20 accuracy, all abstentions; 9/20 instances
  extracted zero capsules (31/43 documents empty), and surviving capsules were
  tech-adjacent fragments, not the queried personal facts. The pack fix is hereby
  **promoted in-scope** (user-endorsed): new task T-L3 drafts a `conversation_v1`
  domain pack (personal facts / preferences / plans / possessions object families,
  salience admitting mundane personal state, supersession rules on same-actor personal
  state, Qwen model ids — never deepseek) plus a `--pack` flag on the adapter threaded
  through ingestion (`Document.domain_pack`) and all pipeline stages; T-L4 reruns
  per-category (two runs: knowledge-update and temporal-reasoning, limit 10 each — the
  run-1 slice also exposed that dataset order is not category-interleaved) for the
  before/after comparison that doubles as the pack-scalability demonstration.
- Cost bounded by `--limit` default 20 (~1–5 oracle docs per instance ≈ well under the
  synthetic benchmark's per-run spend).
- No edits to `run_memory_benchmark.py`, `extraction.py`, `chat.py`, or pack YAMLs.
  **Superseded for `chat.py`/prompts by the T-L5 amendment below** (user-approved
  2026-07-04); `run_memory_benchmark.py` and `extraction.py` stay untouched.

## Amendment — T-L5 answer-path temporal grounding + conflict resolution (2026-07-04)

Full-211 run (partial, 194/211): knowledge-update 0.564, temporal-reasoning 0.224,
88 abstentions (74 on temporal-reasoning) despite 20–26 capsules per instance and zero
empty docs — evidence is retrieved but the answer path is time-blind. Three approved
fixes:

1. **Question-time anchor.** `run_chat_with_context` gains keyword-only
   `as_of: datetime | None = None`, threaded through chat state into `generate_answer`
   and rendered by `build_user_prompt` as a `Current date: YYYY-MM-DD (Weekday)` line
   ahead of the question. Adapter passes the instance's parsed `question_date`.
   Existing callers (`answer_chat`, `_answer_node`, `run_memory_benchmark`) pass
   nothing and get today's date injected (`datetime.now(timezone.utc)`) — relative-time
   questions in production have the same anchoring need.
2. **Dated context blocks.** Both capsule-candidate queries in `chat.py` (hybrid
   retrieval + `_fetch_capsules_by_ids`) additionally select `Document.published_at`;
   `_build_context_block` copies it onto the block; `build_user_prompt` renders
   `Date: YYYY-MM-DD (Weekday)` (or omits the line when null). Weekday included because
   temporal-reasoning questions reference "last Saturday"-style anchors.
3. **Conflict resolution + aggregation recall.** `SYSTEM_PROMPT` in `chat_answer.py`
   instructs: when blocks conflict, resolve via supersession roles, lifecycle_state and
   dates and state the single best-supported answer — never report "conflicting
   evidence" as the answer. `multi_doc` strategy: `top_k_delta` 3→5 and hint extended
   to enumerate-and-count across all blocks for "how many" questions.

Plus a robustness nit: judge call retries once on `LLMError`/`LLMNetworkError` before
recording `autoeval_label: null`.

**Non-goals:** no new question shape, no classifier prompt change, no schema change,
no re-ingestion (documents already carry `published_at`).

**Success criteria:** full suite green (known pre-existing failures only); rerun of the
same 211-question slice shows temporal-reasoning materially above the 0.224 baseline
with abstentions substantially reduced; before/after table in the H7 report.

## Amendment 2 — retrieval fixes R1/R3 (2026-07-04, user-approved)

Evidence (55-question working subset, all temporal-reasoning): matched-pair vs
baseline showed abstentions 25→7 but accuracy 0.385→0.345 under `qwen-flash`
extraction; `agent_runs` shape audit showed **55/61 classify calls routed to
`factoid`** — whose strategy (semantic_similarity 0.6, `top_k_delta=0`) is tuned for
single-fact lookup while these questions need two-plus dated events retrieved
together. Ranking is date-blind: recency scoring uses capsule `created_at`
(ingestion order — noise when a corpus is ingested in one batch).

- **R1 — `temporal` question shape.** `router.py` gains
  `STRATEGIES["temporal"] = RetrievalStrategy(top_k_delta=7, fetch_k_multiplier=6,
  answer_hint=<compute orderings/durations from the block Date lines and the Current
  date; state the arithmetic>)`. `QUESTION_SHAPES` picks it up automatically.
  `classify_intent.py` SYSTEM_PROMPT adds the shape definition (event ordering,
  duration, elapsed-time, date-arithmetic questions) **and narrows `factoid`** — its
  current wording claims "when/what questions about past events", which would keep
  swallowing temporal questions.
- **R3 — event-time recency.** `compute_hybrid_score` and its `recency_min/max`
  computation in `_run_retrieve_capsules` use `published_at` when the candidate has
  one, falling back to `created_at`. Candidates already carry `published_at`
  (T-L5a).

- **R2 — sub-query union retrieval: attempted and reverted 2026-07-04.** Targeted
  post-R1/R4 residue (counting/aggregation and two-event comparisons where cosine
  similarity against the whole question retrieves only one comparandum) by having
  the classifier emit per-entity `sub_queries`, then pooling each sub-query's ANN
  candidates in retrieval. Implemented (`bc8fe83`), full-suite validated, then
  55-subset benchmark-validated against the T-L6+R4 baseline it targeted — it
  regressed: accuracy 0.611→0.574, abstentions 5→8 (9 regressed vs 7 fixed).
  Root cause: pooling all sub-query candidates into one set and reranking globally
  lets whichever entity's sub-query matches more/closer capsules dominate the shared
  top-k and starve the other comparandum — 4/9 regressions flipped straight to
  abstention. Not an implementation bug; a design flaw in pool-then-global-rerank.
  Reverted (`ec1962a`). **Corrected design for a future attempt**: allocate a floor
  per sub-query before any shared rerank (e.g.
  `ceil(effective_top_k / (1 + len(sub_queries)))` guaranteed slots per vector,
  top-up the remainder by global score) so no comparandum can be crowded out. Not
  reattempted now — logged as a follow-up.

- **R4 — render span evidence in the answer prompt (2026-07-04).** Span retrieval
  exists end-to-end (`_build_evidence_map`, pack `source_refs_and_excerpts`,
  `block["evidence"]`) but `build_user_prompt` never renders it — excerpts reach only
  the API citations payload, so the answer model has never seen a span. Failure Mode 1
  (relative dates in capsule text anchored to the wrong "now") needs the raw local
  utterance next to the block's session date. Fix: when a block carries `evidence`,
  render up to 2 excerpts under the capsule text as `Excerpt: <text>` lines
  (existing 280-char caps apply; no new config). Keeps the pack date-normalization
  idea (extraction-time absolute dates) as a held alternative — prompt rendering is
  cheaper and needs no re-ingestion.

**Success criteria:** classifier routes ordering/duration questions to `temporal`
(spot-check via agent_runs); 55-subset run shows accuracy at or above the 0.385
matched baseline with abstentions still ≤ ~15%.
