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
