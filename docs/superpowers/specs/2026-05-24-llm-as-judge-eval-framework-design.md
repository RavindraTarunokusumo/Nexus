# LLM-as-a-Judge Evaluation Framework

**Status:** Design
**Date:** 2026-05-24
**Author:** Brainstormed with Claude (autonomous mode — user offline)
**Phase:** Post-Phase-3, pre-Phase-4 hardening
**Approach selected:** Hybrid — Nexus owns harness, schemas, and persistence; judge prompts borrow rubrics inspired by G-Eval / Ragas / DeepEval but execute through the existing `LLMClient` + observability stack.

## Motivation

Nexus Lite has shipped Phase 3 (claim extraction) and is staging Phase 4 (brief synthesis + grounded query answering). Today there is **no objective, repeatable way to measure output quality** beyond manual spot-checking:

1. Claim extraction quality is implicit — a successful run means the LLM returned schema-valid JSON, *not* that the claims are correct, well-typed, or grounded in the span.
2. Span search (`POST /search/spans`) returns top-k hits with no ground truth for relevance.
3. Phase 4 will introduce briefs and grounded answers with no safety net against hallucinated citations or off-topic synthesis.
4. Prompt edits, model swaps (T2 deepseek-v4-flash ↔ alternatives), or domain-pack tuning currently rely on vibes — there is no regression channel.
5. The Phase 4 brief/query loop will commit to user-visible artefacts; shipping it without a gold-set-backed quality gate is reckless.

This iteration introduces an **LLM-as-a-Judge evaluation framework** that scores Nexus's outputs against a hand-curated gold dataset, persists per-run results, and surfaces pass/fail deltas across prompt or model changes.

## Goals & Non-Goals

### Goals

- Score each evaluable Nexus task (claim extraction, span retrieval, future brief synthesis, future query answering) against gold-standard answers using LLM judges with explicit rubrics.
- Make eval runs **reproducible**: pinned model, pinned gold-set version, deterministic seeding where supported, full prompt provenance.
- Make eval results **queryable**: persist scores in Postgres so we can diff runs, track regressions, and answer "did prompt vN+1 improve groundedness?".
- Reuse the existing observability stack (`run_id`, `agent_runs`, cost tracking) — eval runs are first-class members of the same audit trail as production runs.
- Provide a **CLI surface** (`nexus eval ...`) and **gold-set file format** that a single developer can edit by hand without ceremony.
- Include a **meta-evaluation** step so judge prompts are themselves validated against human labels (Cohen's κ ≥ 0.6 target).

### Non-Goals

- This framework does **not** replace integration tests. Schema-validity, status-transition, and HTTP-contract concerns remain in pytest.
- It is **not** a public-facing dashboard. Output is CLI + JSON + DB rows; visualization can be layered later.
- It is **not** a continuous online evaluator (no sampling production traffic). It is an offline harness driven by a curated gold set.
- It does **not** evaluate retrieval recall against the entire corpus (no relevance judgments at corpus scale). Span retrieval eval is limited to a small set of (query, expected_span_ids) pairs.
- It does **not** ship Phase-4 brief/query judges as runnable rubrics in v1 — only stubs and schemas, since those features don't yet exist. Rubrics for them are designed but gated behind the feature shipping.

## Scope

### In scope (v1)

- New `app/evaluation/` package: `datasets.py`, `runner.py`, `judges.py`, `metrics.py`, `meta_eval.py`
- Alembic migration `0003_evaluation.py` — three new tables: `eval_datasets`, `eval_runs`, `eval_results`
- Gold-set file format (YAML in `evals/gold/<task>/<dataset_name>.yaml`)
- Two production-ready judges:
  - **Claim extraction judge** — scores precision, recall, type-correctness, groundedness for a (document, gold_claims, predicted_claims) triple
  - **Span retrieval judge** — scores nDCG@k, precision@k, and an LLM-judged relevance score for (query, gold_span_ids, retrieved_spans)
- Two stub judges (schema + persistence wired, rubric defined but not invoked until feature ships):
  - **Brief synthesis judge** (faithfulness, coverage, citation-correctness)
  - **Grounded answer judge** (correctness, citation-correctness, refusal-appropriateness, hallucination-rate)
- CLI commands: `nexus eval list`, `nexus eval run <task> <dataset>`, `nexus eval show <run_id>`, `nexus eval diff <run_a> <run_b>`
- Meta-eval workflow: a `evals/human_labels/<task>.yaml` file plus `nexus eval calibrate <task>` command that computes Cohen's κ between judge and human labels
- TODO.md additions for deferred items

### Out of scope (deferred to TODO.md)

- Brief and grounded-answer **rubrics activated** (depends on Phase 4 features shipping)
- Web UI / dashboard
- Online sampling of production traffic
- Multi-judge ensembling (single judge per task in v1)
- Cross-lingual evaluation
- Adversarial / red-team eval set
- Cost-optimization through batching API calls
- Statistical significance testing across runs (bootstrap CIs) — v1 reports raw means
- Auto-bisection of regressions

## Architecture

```
                       evals/                           app/evaluation/
                       ├── gold/                        ├── datasets.py      (load YAML → typed
                       │   ├── claim_extraction/        │                     pydantic models)
                       │   │   ├── ai_tech_v1.yaml      │
                       │   │   └── ...                  ├── runner.py        (orchestrates one
                       │   └── span_retrieval/          │                     eval run end-to-end)
                       │       └── ...                  │
                       └── human_labels/                ├── judges.py        (per-task judge
                           └── claim_extraction.yaml    │                     classes; each owns
                                                        │                     a prompt + schema)
                                                        │
                                                        ├── metrics.py       (deterministic
                                                        │                     metrics: P/R/F1,
                                                        │                     nDCG@k, precision@k)
                                                        │
                                                        └── meta_eval.py     (judge ↔ human
                                                                              agreement, κ)

  CLI: nexus eval run claim_extraction ai_tech_v1
   │
   ▼
  runner.execute_run(task, dataset)
   │   ├── load dataset                                          ┌─────────────────┐
   │   ├── for each example:                                     │ existing stack  │
   │   │   ├── call Nexus under test (HTTP API or in-proc)──────▶│  LLMClient      │
   │   │   ├── compute deterministic metrics                     │  observability  │
   │   │   ├── invoke judge (LLM call via LLMClient) ───────────▶│  agent_runs     │
   │   │   └── persist eval_results row                          │  (run_id, cost) │
   │   └── persist eval_runs summary                             └─────────────────┘
   ▼
  Postgres: eval_datasets, eval_runs, eval_results
   ▲
   │
  CLI: nexus eval show / diff / calibrate
```

## Components

### 1. Datasets (`app/evaluation/datasets.py`)

Loads YAML gold files into typed pydantic models. One model per task:

- `ClaimExtractionExample`: `{example_id, document_id_or_text, gold_claims: list[GoldClaim], notes}`
- `SpanRetrievalExample`: `{example_id, query, gold_span_ids: list[UUID], optional_negative_span_ids, notes}`
- `BriefSynthesisExample` (stub): `{example_id, input_claim_ids, gold_brief_text, required_topics, forbidden_topics, notes}`
- `GroundedAnswerExample` (stub): `{example_id, query, gold_answer, required_citation_claim_ids, refusal_expected: bool, notes}`

A `Dataset` wraps `{name, version, task, examples, checksum}`. Checksum is SHA-256 of the canonical YAML so reruns can prove they used the same data.

### 2. Runner (`app/evaluation/runner.py`)

Single entrypoint: `execute_run(task: EvalTask, dataset: Dataset, system_under_test: SUTConfig) -> EvalRunResult`.

Responsibilities:
- Resolve the SUT — either in-process (preferred; reuses the running event loop and SQLAlchemy session) or HTTP (against a running `nexus serve` instance).
- For each example: call the Nexus task, compute deterministic metrics, invoke the judge, persist a row.
- Aggregate per-example scores into run-level means + std-dev.
- Bind a fresh `run_id` via `extraction_run(...)` context manager so judge LLM calls inherit observability correlation.
- Tolerate per-example failures — log + record `status=error` for that row, continue the run.

### 3. Judges (`app/evaluation/judges.py`)

Each judge is a class with:
- `name` (e.g., `"claim_extraction_judge_v1"`)
- `prompt_template` (Jinja or string-format)
- `output_schema` (pydantic model with score fields + per-field rationale)
- `model_tier` (T3 by default — judge should be stronger than SUT)
- `score(example, prediction) -> JudgeVerdict` method that returns typed scores

#### Claim extraction judge — rubric (active in v1)

For each (gold claim, predicted claim) pair the judge returns:

| Dimension | Scale | Definition |
|---|---|---|
| `match_status` | `exact` \| `partial` \| `missing` \| `spurious` | Did the prediction surface this gold claim? |
| `type_correct` | bool | Was the claim taxonomy label (one of 11) correct? |
| `groundedness` | 0.0–1.0 | Is the claim text supported by the cited span? |
| `factuality` | 0.0–1.0 | Is the claim itself a true statement *as judged from the span text* (not external knowledge)? |
| `rationale` | free text | One-sentence explanation |

Run-level aggregates: precision, recall, F1 (over `match_status`); type-accuracy; mean groundedness; mean factuality; mean rationale length (sanity check that the judge is reasoning, not rubber-stamping).

#### Span retrieval judge — rubric (active in v1)

Two layers run together:
- **Deterministic** (no LLM): precision@k, recall@k, nDCG@k computed from `gold_span_ids` vs. retrieved IDs.
- **LLM-judged relevance** (one call per (query, top_k_spans)): the judge rates each retrieved span on a 0–3 graded relevance scale (0=irrelevant, 3=ideal), producing a graded nDCG.

#### Brief synthesis judge — rubric (stub in v1)

Designed but not invoked until Phase 4 ships briefs:

| Dimension | Scale | Definition |
|---|---|---|
| `faithfulness` | 0.0–1.0 | Every assertion traceable to a source claim |
| `coverage` | 0.0–1.0 | Required topics from gold are addressed |
| `citation_correctness` | 0.0–1.0 | Citations point to claims that actually support the cited sentence |
| `topic_violation` | bool | Brief contains forbidden topics |
| `coherence` | 0.0–1.0 | Reads as a coherent brief, not a bullet dump |

#### Grounded answer judge — rubric (stub in v1)

| Dimension | Scale | Definition |
|---|---|---|
| `correctness` | 0.0–1.0 | Semantically matches gold answer |
| `citation_correctness` | 0.0–1.0 | Citations support the answer |
| `hallucination_rate` | 0.0–1.0 | Fraction of answer sentences with no supporting citation |
| `refusal_appropriate` | bool | If gold expects refusal, did the system refuse? |

### 4. Metrics (`app/evaluation/metrics.py`)

Pure functions, deterministic, no LLM calls:
- `precision_recall_f1(gold_ids, pred_ids) -> tuple[float, float, float]`
- `precision_at_k(gold_ids, ranked_pred_ids, k) -> float`
- `ndcg_at_k(graded_relevances, k) -> float`
- `claim_set_match(gold_claims, pred_claims) -> list[tuple[GoldClaim|None, PredClaim|None, str]]` (the matcher the judge consumes — uses simple lexical + embedding similarity to align before the LLM rates each pair, avoiding O(n·m) LLM calls)

### 5. Meta-evaluation (`app/evaluation/meta_eval.py`)

Validates the judge itself. Workflow:

1. Human (the developer) labels ≥50 (example, prediction) pairs in `evals/human_labels/<task>.yaml` with the same rubric the judge uses.
2. `nexus eval calibrate <task>` runs the judge on those pairs and computes:
   - **Cohen's κ** (for categorical fields like `match_status`, `type_correct`)
   - **Pearson r** (for continuous fields like `groundedness`)
   - **Confusion matrix** for categorical dimensions
3. Target: κ ≥ 0.6 ("substantial agreement") before the judge's verdicts are trusted to gate prompt changes. Below 0.4 → rewrite the rubric.
4. Calibration must be **re-run whenever the judge prompt or judge model changes**. The judge prompt version is stored on the `eval_runs` row.

## Data Model

### `eval_datasets`

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| name | TEXT | e.g., `"ai_tech_v1"` |
| task | TEXT | `claim_extraction`, `span_retrieval`, `brief_synthesis`, `grounded_answer` |
| version | INT | Bumped on schema-breaking edits to gold |
| checksum | TEXT | SHA-256 of canonical YAML |
| example_count | INT | Materialized for fast queries |
| path | TEXT | Repo-relative path |
| created_at | TIMESTAMPTZ | Auto |

Unique constraint on `(name, task, version)`.

### `eval_runs`

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key — also the observability `run_id` |
| dataset_id | UUID | FK → eval_datasets |
| sut_model | TEXT | Model under test (e.g., `deepseek/deepseek-v4-flash`) |
| sut_prompt_version | TEXT | Git SHA of the prompt file at run time |
| judge_name | TEXT | e.g., `claim_extraction_judge_v1` |
| judge_model | TEXT | e.g., `deepseek/deepseek-v4-pro` |
| judge_prompt_version | TEXT | Git SHA of the judge prompt file |
| started_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | Nullable until done |
| status | TEXT | `running`, `completed`, `failed`, `partial` |
| aggregate_scores | JSONB | `{precision: 0.82, recall: 0.71, f1: 0.76, ...}` |
| total_cost_usd | NUMERIC | Sum of judge + SUT cost for this run |
| notes | TEXT | Optional |

Indexes: `dataset_id`, `started_at`.

### `eval_results`

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| run_id | UUID | FK → eval_runs (CASCADE) |
| example_id | TEXT | From the YAML — stable identifier within a dataset |
| sut_output | JSONB | Raw prediction |
| judge_verdict | JSONB | Full structured judge output |
| deterministic_metrics | JSONB | Computed metrics for this example |
| status | TEXT | `scored`, `error`, `skipped` |
| error_message | TEXT | Nullable |
| created_at | TIMESTAMPTZ | Auto |

Indexes: `run_id`, `(run_id, status)`.

## Gold-Set File Format

YAML, hand-editable. One example per list item. Schema enforced by pydantic on load.

```yaml
# evals/gold/claim_extraction/ai_tech_v1.yaml
name: ai_tech_v1
task: claim_extraction
version: 1
description: |
  Hand-curated set of 30 AI/tech articles spanning model_release,
  benchmark_result, funding_event, and pricing_change claim types.
examples:
  - example_id: anthropic_opus_47_release
    # Either provide document_text inline, or reference an ingested document
    document_text: |
      Anthropic today released Claude Opus 4.7, a new flagship model...
    gold_claims:
      - claim_type: model_release
        claim_text: "Anthropic released Claude Opus 4.7"
        # Span of the source text that supports it (char offsets into document_text)
        supporting_span: [0, 52]
        notes: "Lead sentence; unambiguous"
      - claim_type: benchmark_result
        claim_text: "Opus 4.7 scores 79% on SWE-bench Verified"
        supporting_span: [340, 392]
    notes: "Tests basic model_release + benchmark co-occurrence"
```

## CLI Surface

| Command | Purpose |
|---|---|
| `nexus eval list-datasets` | List registered gold sets with version + example count |
| `nexus eval list-runs [--task X] [--dataset Y]` | Show recent runs |
| `nexus eval run <task> <dataset> [--sut-model M] [--judge-model M] [--note "..."]` | Execute an eval run end-to-end; prints summary table + saves `run_id` |
| `nexus eval show <run_id> [--per-example]` | Show aggregate scores; with flag, dump all per-example verdicts |
| `nexus eval diff <run_a> <run_b>` | Side-by-side aggregate comparison + list of examples that changed verdicts |
| `nexus eval calibrate <task>` | Run meta-eval; print κ / r and confusion matrix |
| `nexus eval register-dataset <yaml_path>` | Insert / update `eval_datasets` row, recompute checksum |

All commands support `--json` for machine output.

## Workflow: Adding a New Gold Example

1. Edit `evals/gold/<task>/<dataset>.yaml`, append an example, bump `version`.
2. `nexus eval register-dataset evals/gold/...` — recomputes checksum, validates schema.
3. `nexus eval run <task> <dataset>` — sanity-check that the new example scores reasonably under the current SUT.
4. If the judge mis-scores it, add (example, prediction, human_label) to `evals/human_labels/<task>.yaml` and re-run `nexus eval calibrate`.

## Workflow: Prompt or Model Change

1. Edit prompt or change `t2_model` in config.
2. `nexus eval run claim_extraction ai_tech_v1 --note "experiment: tighter system prompt"`.
3. `nexus eval diff <baseline_run_id> <new_run_id>` — read the deltas.
4. If aggregate F1 ↑ and no individual example regresses critically → ship.

## Cost Model

Per eval run, two LLM cost contributors:
- **SUT cost**: one extraction (or retrieval) call per example. Already tracked via `agent_runs.cost_estimate`.
- **Judge cost**: one judge call per example (claim extraction) or one per query (retrieval). Judge runs at T3 by default → ~3× cost per token of T2, but operates on smaller inputs (just the claims/spans, not full docs).

Rough estimate for a 30-example claim_extraction run:
- SUT (T2): 30 docs × ~5 spans × ~2k tokens ≈ 300k tokens ≈ $0.09
- Judge (T3): 30 examples × ~3k tokens ≈ 90k tokens ≈ $0.08
- **Total: ~$0.17 per run**

Budget gate: `runner.execute_run` accepts `max_cost_usd` (default $1.00) and aborts before exceeding it.

## Error Handling

- **Judge returns invalid JSON** → 1 correction prompt retry (same pattern as `LLMClient.complete_json`), then `status=error` on the row, run continues.
- **SUT fails** (e.g., 503 from OpenRouter) → `status=error`, continue.
- **Dataset checksum mismatch at run-time** → abort with clear error; user must `register-dataset` to acknowledge the change.
- **Judge cost runaway** → budget gate aborts mid-run, writes `status=partial` with whatever results landed.
- All errors recorded under the same `run_id` and surfaced via `nexus eval show`.

## Reproducibility Guarantees

A run is reproducible if you fix:
- `dataset_checksum` (enforced by load-time check)
- `sut_model` + `sut_prompt_version` (git SHA of the prompt file)
- `judge_model` + `judge_prompt_version`
- Temperature (defaulted to 0.0 for both SUT and judge in eval mode; overridable via flag)

These four fields are persisted on every `eval_runs` row.

## Validation Plan

The framework itself ships with tests:
- `tests/evaluation/test_datasets.py` — YAML round-trip, checksum stability, schema validation
- `tests/evaluation/test_metrics.py` — precision/recall/F1/nDCG against known fixtures
- `tests/evaluation/test_runner.py` — mocked LLMClient, verify per-example error tolerance, budget gate, `run_id` propagation, `eval_results` persistence
- `tests/evaluation/test_judges.py` — judge prompt produces parseable JSON against a captured fixture; rubric fields present
- `tests/evaluation/test_meta_eval.py` — κ and r calculations against synthetic agreement matrices

Manual validation before declaring v1 done:
1. Build the initial `ai_tech_v1` gold set with ≥30 examples covering all 11 claim types.
2. Build the initial `span_retrieval_v1` gold set with ≥20 (query, expected_span_ids) pairs.
3. Build `evals/human_labels/claim_extraction.yaml` with ≥50 hand-labeled (example, prediction) pairs.
4. Run `nexus eval calibrate claim_extraction` — confirm κ ≥ 0.6 on `match_status` and `type_correct`.
5. Run a full baseline `nexus eval run claim_extraction ai_tech_v1` and record the run_id in `docs/insights.md` as the baseline reference.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Judge is biased toward verbose / structured outputs | Meta-eval calibration; explicit rubric forbidding length-based scoring; mix gold examples with deliberately terse-but-correct claims |
| Judge model and SUT model are the same family → echo-chamber agreement | Default judge tier = T3 (`deepseek-v4-pro`), default SUT tier = T2 (`deepseek-v4-flash`); allow swapping judge to a different vendor via config |
| Gold set drifts in quality over time | Versioned datasets + checksum; bumps required for any edit; old datasets remain queryable for historical comparison |
| Judge cost dominates | Budget gate; deterministic metrics where possible; align claim pairs lexically before LLM scoring instead of O(n·m) cross-pair calls |
| LLM-judged scores look precise but aren't | Always pair with deterministic metrics; report std-dev on aggregates; require κ ≥ 0.6 before trusting judge verdicts to gate decisions |
| Phase-4 features ship and stub rubrics never get activated | TODO.md entry per stub; activation gated on a checklist included with the brief/query PR |

## Open Questions

1. Should retrieval eval also evaluate the **embedding model** in isolation (e.g., MTEB-style) or only the end-to-end query → spans pipeline? **Proposal: end-to-end only in v1**; embedding-model benchmarking is covered by the separate benchmarks spec.
2. Should we record judge raw responses (full text) or only parsed verdicts? **Proposal: store full parsed JSON in `judge_verdict`, store raw text in `agent_runs.response_text` via the existing observability path** — no new column needed.
3. How do we handle ground-truth disagreements between two human labelers? **Proposal: v1 is single-labeler (the developer)**; multi-labeler agreement is a future iteration.
4. Should `eval_results.sut_output` store the post-validation prediction or the raw LLM string? **Proposal: post-validation typed prediction**; raw string lives in `agent_runs` as today.

## Deliverable Checklist

- [ ] `app/evaluation/` package with five modules
- [ ] Migration `0003_evaluation.py` (3 tables, indexes)
- [ ] `evals/gold/claim_extraction/ai_tech_v1.yaml` (≥30 examples)
- [ ] `evals/gold/span_retrieval/queries_v1.yaml` (≥20 examples)
- [ ] `evals/human_labels/claim_extraction.yaml` (≥50 pairs)
- [ ] Two active judges + two stub judges
- [ ] CLI commands wired into `nexus eval` sub-app
- [ ] Test suite (≥ 5 test files)
- [ ] Calibration run logged in `docs/insights.md` with baseline run_id
- [ ] `docs/index.md` updated with link to this framework
- [ ] TODO.md entries for deferred items (dashboard, brief/query activation, ensembling, sig-testing)

## Cross-References

- Companion spec: `docs/superpowers/specs/2026-05-24-public-benchmarks-design.md` (to be written) — covers running Nexus components against external, third-party benchmarks. The two specs are complementary: this one measures Nexus on *Nexus-specific* tasks against hand-curated gold; the benchmarks spec measures Nexus's underlying components (embedding model, claim-extraction model) against *industry-standard* datasets so we can compare to published numbers.
- Builds on: `2026-05-21-observability-design.md` — eval runs reuse `run_id`, `agent_runs`, and cost tracking.
- Anticipates: Phase 4 (brief synthesis, grounded answers) — stub judges + tables shipped now, activated when those features land.
