# Public Benchmarks Evaluation Framework

**Status:** Design
**Date:** 2026-05-24
**Author:** Brainstormed with Claude (autonomous mode — user offline)
**Phase:** Post-Phase-3, pre-Phase-4 hardening
**Approach selected:** Hybrid leaderboard-aligned — use established public benchmarks (MTEB, FEVER, HaluEval, CLEF CheckThat!) for component quality, run them through Nexus's runner so results land in the same Postgres tables as the LLM-as-Judge framework, and report both component-level and pipeline-level numbers.

## Motivation

The companion spec ([2026-05-24-llm-as-judge-eval-framework-design.md](2026-05-24-llm-as-judge-eval-framework-design.md)) introduces an LLM-as-a-Judge framework that scores Nexus on *Nexus-specific, hand-curated* gold sets. That measures whether the system behaves the way the developer wants — but it cannot answer:

1. **Are we using a competitive embedding model?** `BAAI/bge-small-en-v1.5` was state-of-the-art for a 384-dim model in 2023; the small-model leaderboard has moved. Without MTEB numbers we can't tell if a swap is worth it.
2. **Is our claim-extraction model competitive on standard fact-checking tasks?** `deepseek-v4-flash` may dominate benchmarks at its price point, or it may be median. We don't know.
3. **Does Nexus's wrapping (chunking, system prompt, output schema validation) help or hurt model quality vs. calling the model raw?** This is the most consequential question for product decisions, and it can only be answered by running benchmarks **both** at the component layer (raw model call) and at the pipeline layer (through Nexus code).
4. **When we swap T1 or T2 models in the future, what's our quality floor?** Without baseline benchmark numbers from the current configuration there is no reference point.
5. **Is judge-derived "quality" from Spec #1 actually correlated with externally-recognized quality?** If our LLM-as-Judge says output is great but FEVER accuracy is 40%, the judge is broken. Public benchmarks act as a sanity layer over the in-house judge.

This iteration introduces a **public-benchmarks evaluation framework**, complementary to the LLM-as-Judge framework, that measures Nexus's components against established external datasets with published leaderboard numbers.

## Goals & Non-Goals

### Goals

- Run **MTEB Retrieval + STS subset** against the configured T1 embedding model and produce numbers directly comparable to the MTEB leaderboard.
- Run **FEVER + HaluEval** against the configured T2 model, both at the **component layer** (raw model call) and at the **pipeline layer** (through Nexus's claim-extraction code path).
- Adapt **CLEF CheckThat! Task 1 (Check-worthiness) + Task 2 (Verified-claim retrieval)** as the closest available external proxy for news-article claim extraction.
- Persist all results in shared tables so the LLM-as-Judge eval results and public-benchmark results can be cross-queried by run, by model, by date.
- Reuse Spec #1's CLI surface where possible — `nexus eval bench ...` sub-commands, same `eval_runs`-shaped persistence (with a `kind` discriminator).
- Stub Phase-4-only benchmarks (**HotpotQA** for grounded QA, **RAGTruth** for RAG hallucination, **ASQA** for long-form citation) with the runner + adapters wired but the eval gated until the SUT exists.
- Ship a single command (`nexus eval bench baseline`) that runs the full active benchmark suite end-to-end and produces a single summary report — this is the **regression gate** for model swaps.

### Non-Goals

- We do **not** intend to publish benchmark numbers to the MTEB leaderboard. These numbers are internal and decision-support only.
- We do **not** train or fine-tune any model based on benchmark results. Read-only evaluation.
- We do **not** run full MTEB (56 datasets) by default — too costly, too slow. A focused, retrieval-relevant subset is the default.
- We do **not** replace the LLM-as-Judge framework. Public benchmarks measure *task-level* quality on external data; in-house judges measure *Nexus-specific* output quality on curated data. Both are needed.
- We do **not** evaluate against benchmarks that require external API keys beyond OpenRouter (e.g., proprietary evaluation services). Datasets must be Hugging Face Hub-accessible or directly downloadable.
- We do **not** implement Phase-4 benchmark runners (HotpotQA / RAGTruth / ASQA) in v1 — adapters and table rows only.

## Scope

### In scope (v1)

- New `app/evaluation/benchmarks/` sub-package: `mteb_runner.py`, `fever_runner.py`, `halueval_runner.py`, `checkthat_runner.py`, `adapters.py`, `loaders.py`
- Alembic migration `0004_benchmarks.py` — extends `eval_runs` with a `kind` column (`judge` | `benchmark`), adds a `benchmark_runs` materialized summary view (or a `benchmark_metadata` JSONB on `eval_runs`), no new tables required if discriminator + JSONB approach is taken (**preferred**)
- Dependencies added: `mteb >= 1.12` (Python package), `datasets >= 2.18` (Hugging Face), `evaluate >= 0.4` for standard metric implementations
- Benchmark cache directory: `evals/benchmarks/cache/` (gitignored) for downloaded HF datasets; `evals/benchmarks/manifests/` (committed) for dataset version pins
- Five active benchmark runners (T1 retrieval, T1 STS, FEVER, HaluEval, CheckThat!)
- Three stub runners (HotpotQA, RAGTruth, ASQA) — adapters present, runners raise `NotImplementedError` with a clear message about Phase-4 dependency
- Pipeline-vs-component differentiation: every T2 benchmark runs in two modes — `component` (raw `LLMClient` call with benchmark's prompt) and `pipeline` (full Nexus extraction path with Nexus's prompt). Results are tagged so comparison is trivial.
- CLI commands under `nexus eval bench ...`
- Aggregate "baseline" report — `nexus eval bench baseline --output md` produces a markdown table comparable to leaderboard format
- TODO.md additions for deferred items

### Out of scope (deferred to TODO.md)

- Full MTEB run (all 56 datasets)
- Multi-lingual benchmarks (MIRACL, XOR, etc.)
- Phase-4 benchmark runners (HotpotQA, RAGTruth, ASQA) activated
- Reranker benchmark (we don't ship a reranker yet)
- Long-context benchmarks (RULER, LongBench) — not relevant until Nexus uses long-context features
- Adversarial / red-team benchmarks (PromptBench, AdvGLUE)
- Continuous benchmarking in CI — v1 is on-demand only
- Statistical significance testing across benchmark runs (bootstrap CIs)
- Embedding-only retrieval ablations (sweeping `top_k`, distance metric)
- Cost-per-quality Pareto curves across alternative T2 models

## Selected Benchmarks

### T1 — Embedding Model (`BAAI/bge-small-en-v1.5`)

#### MTEB Retrieval Subset (active)

Four BEIR datasets chosen for **direct relevance to Nexus's span-retrieval use case** (English, factual, short-passage retrieval):

| Dataset | Why chosen | Metric |
|---|---|---|
| `MSMARCO` | Web-scale passage retrieval — the gold standard | nDCG@10 |
| `NFCorpus` | Medical / scientific passages — tests technical content | nDCG@10 |
| `SciFact` | Scientific claim retrieval — overlaps with claim extraction | nDCG@10 |
| `TREC-COVID` | Topical retrieval over an evolving corpus — mirrors Nexus's "fresh news" use case | nDCG@10 |

Default subset size: **dev split, capped at 1000 queries per dataset** (configurable via `--max-queries`). Full BEIR splits are available with `--full`.

#### MTEB STS Subset (active)

Two STS datasets for semantic similarity quality:

| Dataset | Metric |
|---|---|
| `STS-Benchmark` | Spearman correlation |
| `STS22` (English subset) | Spearman correlation |

### T2 — Claim Extraction Model (`deepseek/deepseek-v4-flash`)

#### FEVER (active)

**Fact Extraction and VERification.** 185k human-verified claims paired with Wikipedia evidence. Closest large-scale public proxy for what Nexus does (claim ↔ evidence link).

- **Task framing for component layer**: Given (claim, candidate evidence sentences), classify `SUPPORTS` / `REFUTES` / `NOT ENOUGH INFO`. Three-class accuracy + FEVER score (label + evidence correctness).
- **Task framing for pipeline layer**: Treat the evidence document as a "Nexus document," run claim extraction, then check whether the model surfaces the FEVER gold claim with the correct stance. This is an **adapter**, not a literal FEVER run — we report it as `FEVER-adapted-pipeline` to avoid confusion with leaderboard numbers.
- Default subset: **shared dev split, capped at 500 examples** (configurable). Full dev set with `--full`.

#### HaluEval (active)

**Hallucination Evaluation Benchmark.** 35k samples across QA, dialogue, and summarization, each with a known hallucinated and non-hallucinated response. Tests whether the model can *detect* hallucination.

- **Task framing for component layer**: Given (input, two candidate responses, one hallucinated), classify which is hallucinated. Binary accuracy.
- **Task framing for pipeline layer**: Treat each input as a Nexus document, extract claims, then check whether any extracted claim matches the hallucinated content (a "false positive" — extracting fabricated information). Report `HaluEval-pipeline-false-positive-rate`.
- Default subset: **QA + summarization tasks, 500 examples total** (we skip dialogue — not Nexus's domain).

#### CLEF CheckThat! 2023 (active, adapted)

The closest existing public benchmark to Nexus's actual task ("extract verifiable claims from news articles"). Two relevant subtasks:

| Subtask | Use |
|---|---|
| Task 1A — Check-worthiness | Binary classification: is this sentence a check-worthy claim? Maps directly to Nexus's filter for "what counts as a claim." |
| Task 2 — Verified claim retrieval | Given a check-worthy claim, retrieve the matching verified claim from a database. Tests retrieval-style alignment. |

- **Task framing for component layer**: Direct binary classification (Task 1A); retrieval over the provided claim DB (Task 2).
- **Task framing for pipeline layer**: Run Nexus's claim extraction on the CheckThat! source articles; compute precision/recall against gold check-worthy sentences. Report `CheckThat-pipeline-precision` and `-recall`.
- Default subset: **English-only**, full test split (~1k sentences). CheckThat! is small enough to run in full.

### Phase-4 Stub Benchmarks (not active in v1)

| Benchmark | Future SUT | Why stub now |
|---|---|---|
| `HotpotQA` (distractor setting) | Phase-4 grounded query answering | Adapter ready so a single PR activates it once `/query` ships |
| `RAGTruth` | Phase-4 grounded query answering + brief synthesis | Industry-standard RAG hallucination measurement |
| `ASQA` | Phase-4 brief synthesis (long-form) | Long-form ambiguous QA with citations — matches brief format |

Stub runners exist with adapters wired, but `execute()` raises `NotImplementedError("Phase 4 feature not shipped — see TODO.md")`.

## Architecture

```
                                           ┌────────────────────────────────────────────┐
                                           │  app/evaluation/                           │
                                           │  ├── runner.py        (from Spec #1)       │
                                           │  ├── judges.py        (from Spec #1)       │
   nexus eval bench run mteb-retrieval ──▶ │  ├── benchmarks/                           │
                                           │  │   ├── mteb_runner.py                    │
                                           │  │   ├── fever_runner.py                   │
                                           │  │   ├── halueval_runner.py                │
                                           │  │   ├── checkthat_runner.py               │
                                           │  │   ├── adapters.py   (component vs       │
                                           │  │   │                  pipeline mode)     │
                                           │  │   └── loaders.py    (HF dataset cache,  │
                                           │  │                      checksum, subset)  │
                                           │  └── reporting.py     (baseline summary,   │
                                           │                        leaderboard table)  │
                                           └────────────────────────────────────────────┘
                                                          │
                                                          ▼
                                           ┌────────────────────────────────────────────┐
                                           │  shared persistence (Spec #1 tables)       │
                                           │   eval_runs  (kind='benchmark', plus       │
                                           │               benchmark_metadata JSONB)    │
                                           │   eval_results (per-example rows)          │
                                           └────────────────────────────────────────────┘
                                                          ▲
                                                          │
   nexus eval bench baseline ──────────────────────────────┘
                  ▲
                  │
   nexus eval bench compare <run_a> <run_b>
   nexus eval bench leaderboard <run_id> --output md
```

The framework is a **horizontal extension** of Spec #1's runner. Persistence tables are shared; the `eval_runs.kind` discriminator distinguishes a judge run from a benchmark run; `benchmark_metadata` JSONB on `eval_runs` carries benchmark-specific fields (`dataset_split`, `max_queries`, `mode='component'|'pipeline'`, `published_leaderboard_score`, etc.).

## Components

### 1. Loaders (`app/evaluation/benchmarks/loaders.py`)

Wraps Hugging Face `datasets` for benchmark download + caching:

- `load_mteb_task(task_name: str, split: str, max_examples: int | None) -> Dataset`
- `load_fever(split, max_examples) -> Dataset`
- `load_halueval(task: Literal['qa', 'summarization'], max_examples) -> Dataset`
- `load_checkthat(year: int, subtask: str, lang: str = 'en') -> Dataset`

Each loader:
- Downloads to `evals/benchmarks/cache/<dataset>/<version>/`
- Records dataset HF revision SHA in `evals/benchmarks/manifests/<dataset>.yaml`
- Refuses to run if the cache hash doesn't match the manifest unless `--update-manifest` is passed
- Returns typed examples consumable by adapters

### 2. Adapters (`app/evaluation/benchmarks/adapters.py`)

For T2 benchmarks, two adapter classes per benchmark — `<Benchmark>ComponentAdapter` and `<Benchmark>PipelineAdapter`. They take a benchmark example and produce a prediction in the format the metric expects.

- **Component adapter**: builds the benchmark's canonical prompt, calls `LLMClient.complete_json` directly with that prompt, parses the response into the benchmark's expected structure.
- **Pipeline adapter**: feeds the benchmark example through Nexus's actual claim-extraction path (chunking → span building → `extraction.run_with_context`), then derives the benchmark's expected output from Nexus's emitted claims.

This split is critical for the "does Nexus's wrapping help or hurt?" question. Both modes share the same metric computation so the only varying axis is the prompt + code path.

### 3. Benchmark Runners

Each `<benchmark>_runner.py` exposes:

```
class BenchmarkRunner:
    name: str                           # "mteb-retrieval-msmarco" etc.
    component_supported: bool           # True for T2, False for T1
    pipeline_supported: bool
    leaderboard_url: str | None         # For report headers

    async def execute(
        self,
        sut: SUTConfig,
        mode: Literal['component', 'pipeline', 'both'],
        max_examples: int | None,
    ) -> BenchmarkRunResult
```

`BenchmarkRunResult` holds per-example predictions, ground-truth, computed metric, and optional comparison to a published number.

### 4. Reporting (`app/evaluation/reporting.py`)

- `render_baseline_markdown(run_ids: list[UUID]) -> str` — produces a leaderboard-style markdown table:

  ```
  | Benchmark              | Mode      | Metric    | Score | Published | Δ    |
  |------------------------|-----------|-----------|-------|-----------|------|
  | MTEB-MSMARCO           | -         | nDCG@10   | 0.412 | 0.405     | +0.7 |
  | FEVER-component        | component | accuracy  | 0.681 | 0.730     | -4.9 |
  | FEVER-pipeline         | pipeline  | accuracy  | 0.652 | -         | -    |
  | HaluEval-QA-component  | component | accuracy  | 0.724 | 0.770     | -4.6 |
  ```

- `render_run_diff(run_a, run_b) -> str` — side-by-side delta for model swaps.

### 5. MTEB Integration

The official `mteb` Python package handles MTEB evaluation natively. We provide an adapter so it calls our `LLMClient`-wrapped embedding interface (the same path Nexus uses in production), not the raw `sentence-transformers` interface. This way:

- The numbers reflect how Nexus actually uses the model.
- Any future change to embedding plumbing (batching, normalization, prefix prompts) is captured.

## Data Model

**No new tables.** Extends `eval_runs` from Spec #1:

```sql
-- migration 0004_benchmarks.py
ALTER TABLE eval_runs ADD COLUMN kind TEXT NOT NULL DEFAULT 'judge';
ALTER TABLE eval_runs ADD COLUMN benchmark_metadata JSONB;
ALTER TABLE eval_runs ADD CONSTRAINT eval_runs_kind_check
    CHECK (kind IN ('judge', 'benchmark'));
CREATE INDEX eval_runs_kind_idx ON eval_runs (kind);
```

`benchmark_metadata` shape:
```yaml
benchmark_name: "MTEB-MSMARCO"
benchmark_version: "v1.12.0"            # mteb package version
dataset_hf_revision: "abc123..."        # HF dataset SHA
mode: "component"                       # or "pipeline" or "n/a" for T1
subset: { split: "dev", max_queries: 1000 }
sut_component: "T1" | "T2"
published_leaderboard_score: 0.405      # if known; nullable
published_leaderboard_url: "https://..."
metric_name: "nDCG@10"
```

`eval_results` rows for benchmark runs use the same schema; `sut_output` holds the prediction, `judge_verdict` is null (no judge for objective benchmarks), `deterministic_metrics` holds the metric. The `judge_*` columns being null is the visual signal that this is a benchmark result.

## Gold-Set / Dataset Format

Benchmarks use upstream dataset formats directly (FEVER JSON-L, HuggingFace `Dataset` objects, MTEB-native loaders). No hand-curated YAML for benchmarks — that's Spec #1's territory.

The **manifest file** is what we own:

```yaml
# evals/benchmarks/manifests/fever.yaml
dataset: fever
hf_repo: fever
hf_revision: 6f64a8d2e9...
loaded_split: dev
max_examples_default: 500
license: CC-BY-SA-3.0
published_baselines:
  - model: "DeBERTa-v3-large (FEVER paper SOTA)"
    score: 0.880
    metric: "FEVER score"
    url: "https://fever.ai/2018/leaderboard.html"
last_verified: "2026-05-24"
```

Manifests are committed; cache directories are gitignored. CI (when added) will fail if a benchmark is run with a non-manifest HF revision.

## CLI Surface

| Command | Purpose |
|---|---|
| `nexus eval bench list` | List available benchmark runners with `active`/`stub` status |
| `nexus eval bench run <name> [--mode component\|pipeline\|both] [--max-examples N] [--note ...]` | Execute a single benchmark; prints summary + saves `run_id` |
| `nexus eval bench baseline [--output md\|json]` | Run the full active suite end-to-end; renders leaderboard table |
| `nexus eval bench show <run_id> [--per-example]` | Show aggregate + per-example details |
| `nexus eval bench compare <run_a> <run_b>` | Diff two runs (e.g., before/after model swap) |
| `nexus eval bench leaderboard <run_id> --output md` | Render leaderboard-style markdown comparable to published numbers |
| `nexus eval bench update-manifest <benchmark>` | Refresh `manifests/<benchmark>.yaml` to current HF revision (requires explicit flag) |

All commands accept `--json` for machine-readable output. All commands share the `eval_runs` persistence used by Spec #1's `nexus eval ...` family, so `nexus eval list-runs --kind benchmark` works from day one.

## Workflow: Validating a Model Swap

1. Capture baseline: `nexus eval bench baseline --note "v0 baseline: bge-small + deepseek-v4-flash"` → record run_id in `docs/insights.md`.
2. Edit `app/config.py` to point T2 (or T1) at the candidate model.
3. `nexus eval bench baseline --note "candidate: <new-model>"` → new run_id.
4. `nexus eval bench compare <baseline_id> <candidate_id>` — reads aggregate deltas across all benchmarks.
5. **Decision rule**: swap is approved if (a) no benchmark regresses >5 percentage points and (b) at least one benchmark improves >2 percentage points and (c) judge-derived F1 from Spec #1 does not regress >3 points on `ai_tech_v1`. Otherwise, reject or investigate.
6. Optional: run Spec #1's `nexus eval run claim_extraction ai_tech_v1` on the candidate to confirm the in-house judge agrees with the benchmark verdict. If they disagree by >10%, recalibrate the judge.

## Workflow: Onboarding a New Benchmark

1. Identify the benchmark; confirm dataset is HF-accessible and license permits internal use.
2. Add `evals/benchmarks/manifests/<name>.yaml` with current HF revision + published baselines.
3. Implement `app/evaluation/benchmarks/<name>_runner.py` with `BenchmarkRunner` interface.
4. Add adapter(s) — component, pipeline, or both.
5. Add to the "active suite" registry if it should run in `bench baseline` (or leave standalone).
6. Update the leaderboard renderer if metric is new.
7. Cross-link from `docs/insights.md`.

## Cost Model

| Benchmark | Mode | Default examples | Approx tokens | Approx cost |
|---|---|---|---|---|
| MTEB-Retrieval (4 datasets) | n/a (T1, local) | 4×1000 queries | local CPU/GPU, no LLM | **$0** |
| MTEB-STS (2 datasets) | n/a (T1, local) | ~10k pairs | local | **$0** |
| FEVER | component | 500 | ~500×1.5k = 750k | **~$0.23** |
| FEVER | pipeline | 500 | ~500×3k = 1.5M | **~$0.45** |
| HaluEval (QA+sum) | component | 500 | ~500×1.5k = 750k | **~$0.23** |
| HaluEval | pipeline | 500 | ~500×3k = 1.5M | **~$0.45** |
| CheckThat! 1A | component | ~1000 | ~1000×0.5k = 500k | **~$0.15** |
| CheckThat! 2 | retrieval | n/a (T1) | local | **$0** |
| **Full `bench baseline`** | — | — | ~5M | **~$1.50** |

(Costs assume T2 at ~$0.30/M total tokens, current OpenRouter pricing for `deepseek-v4-flash`.)

Budget gate: `runner.execute_run` (shared from Spec #1) enforces `max_cost_usd`. Default for `bench baseline` is **$5.00** to leave headroom for retries.

## Reproducibility Guarantees

A benchmark run is reproducible if you fix:
- `dataset_hf_revision` (enforced at load time against manifest)
- `mteb` package version (recorded in `benchmark_metadata.benchmark_version`)
- `sut_model` + `sut_prompt_version` (git SHA, same mechanism as Spec #1)
- Temperature (0.0 default, overridable)
- `max_examples` and ordering seed (deterministic sample selection — first N after a fixed sort key)

These fields are persisted on every `eval_runs.benchmark_metadata` row.

## Validation Plan

The framework itself ships with tests:
- `tests/evaluation/benchmarks/test_loaders.py` — manifest checksum enforcement, sample size capping, HF revision mismatch raises
- `tests/evaluation/benchmarks/test_adapters.py` — component vs pipeline adapters produce same-shape output, mocked LLMClient
- `tests/evaluation/benchmarks/test_runners.py` — fixture dataset of 10 examples per benchmark, end-to-end run hits persistence
- `tests/evaluation/test_reporting.py` — markdown table renders, deltas computed correctly, leaderboard URL emitted

Manual validation before declaring v1 done:
1. Run `nexus eval bench baseline` end-to-end on a clean environment; total cost ≤ $2.00.
2. Confirm MTEB-MSMARCO score is within ±0.02 nDCG@10 of the published `bge-small-en-v1.5` MTEB leaderboard number (sanity that integration is correct).
3. Confirm FEVER-component three-class accuracy is within published `deepseek-v4-flash` range (or, if no published number, within ±5 points of a same-tier reference model).
4. Run a deliberate "regression" — temporarily change the T2 prompt to remove the "be concise" instruction — and verify `bench baseline` detects it via the comparison report.
5. Log the baseline run_ids (one per active benchmark) in `docs/insights.md` as the "v1 baseline" reference.
6. Run `nexus eval bench compare` between the v1 baseline and a deliberate prompt regression to confirm the comparison renderer works end-to-end.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| HF dataset version drifts (FEVER/HaluEval get re-uploaded) | Manifest pin + `--update-manifest` gate; load fails on mismatch |
| MTEB package API changes between minor versions | Pin `mteb >= 1.12, < 2.0` in `pyproject.toml`; integration test catches breaks |
| Pipeline-mode adapter for FEVER is an *adaptation*, not the real FEVER task — risk of over-interpreting numbers | Renderer always labels adapted benchmarks with `-pipeline` suffix; published-baseline column shows `-` for adapted results |
| Public benchmarks may not reflect Nexus's news-claim use case well (FEVER is Wikipedia, HaluEval is generic) | CheckThat! is the closest news-claim proxy; framework explicitly pairs public benchmarks with Spec #1's in-house judge for triangulation |
| Cost runaway from running full splits accidentally | Two-layer guard: per-runner default `max_examples`, plus overall `bench baseline` budget gate at $5 |
| HF dataset access blocked (rate-limit, downtime) | Loaders cache to disk; once downloaded, runs are offline. Manifest indicates last verified date |
| Embedding model swap requires recomputing all production span embeddings (not just running a benchmark) | Spec calls out this dependency in the "model swap workflow"; out of scope for benchmark spec but flagged so a swap PR includes the reindex step |
| CheckThat! corpus is small (~1k sentences English) → high variance | Report std-dev across the run; flag this benchmark as "low-signal" in reporting; use as a secondary indicator only |
| Benchmark scores diverge from in-house judge (Spec #1) and we don't know which to trust | Documented decision rule: investigate, do not auto-resolve. Judge calibration κ + benchmark numbers together inform the call |
| Local MTEB run requires GPU for reasonable speed; CI / dev environments may not have one | MTEB runs CPU-acceptably for the chosen subset sizes (~30 min); document expected wall-clock per benchmark |

## Open Questions

1. **Should `pipeline` mode for FEVER feed the full evidence document or just the gold evidence sentences?** Proposal: **full document** — that's what Nexus sees in production. The benchmark adapter records both inputs so we can ablate later.
2. **Should we run benchmarks against the production database or a sandbox?** Proposal: **sandbox**. Benchmark runs ingest test documents and produce test claims; mixing into production pollutes the corpus. Provide `--benchmark-db-url` override; default to a separate `nexus_bench` database via Docker Compose profile.
3. **For embedding swaps, should the benchmark also re-embed Nexus's production corpus and run a recall test against a held-out query set?** Proposal: **out of scope for v1**, but TODO.md entry — this is a "Nexus-data benchmark" that bridges public benchmarks and in-house gold. Probably belongs as a new Spec #1 dataset, not here.
4. **Should `bench baseline` block on Phase-4 stubs (i.e., fail loudly until they're activated)?** Proposal: **no** — print a "skipped" line for each stub. Activation lands with the corresponding Phase-4 PR.
5. **Do we need a CI integration in v1?** Proposal: **no, on-demand only**. CI cost + flakiness from external HF downloads outweighs benefit at this stage. Reconsider after Phase 4.

## Deliverable Checklist

- [ ] `app/evaluation/benchmarks/` sub-package (5 modules)
- [ ] `app/evaluation/reporting.py`
- [ ] Migration `0004_benchmarks.py` (extends `eval_runs`)
- [ ] Manifests for: MTEB-MSMARCO, MTEB-NFCorpus, MTEB-SciFact, MTEB-TREC-COVID, MTEB-STSBenchmark, MTEB-STS22, FEVER, HaluEval, CheckThat!
- [ ] Stub manifests + runners for HotpotQA, RAGTruth, ASQA
- [ ] CLI commands wired into `nexus eval bench` sub-app
- [ ] Test suite (≥ 4 test files under `tests/evaluation/benchmarks/`)
- [ ] `pyproject.toml` dependency additions: `mteb`, `datasets`, `evaluate` (pinned versions)
- [ ] `evals/benchmarks/cache/` added to `.gitignore`
- [ ] Baseline `bench baseline` run logged in `docs/insights.md` with run_ids
- [ ] `docs/index.md` updated with link to this framework
- [ ] TODO.md entries for deferred items (full MTEB, multi-lingual, Phase-4 activation, CI integration, recall benchmark on production corpus)
- [ ] Cross-reference link added in Spec #1's "Cross-References" section (already present at the expected path — symmetric link reciprocated here)

## Cross-References

- Companion spec: [2026-05-24-llm-as-judge-eval-framework-design.md](2026-05-24-llm-as-judge-eval-framework-design.md) — the two specs are complementary:
  - **LLM-as-Judge framework** measures Nexus on *Nexus-specific* hand-curated gold; flexible rubrics; catches product-quality regressions; trusts a judge model.
  - **Public benchmarks framework** (this doc) measures Nexus's components on *industry-standard* datasets; rigid metrics; catches model-quality regressions; comparable to leaderboards.
  - Both share the `eval_runs` / `eval_results` persistence and the `nexus eval ...` CLI namespace.
- Builds on: [2026-05-21-observability-design.md](2026-05-21-observability-design.md) — benchmark runs flow through `LLMClient` so `agent_runs` records every call with `run_id` correlation.
- Anticipates: Phase 4 (brief synthesis, grounded answers) — HotpotQA / RAGTruth / ASQA stubs ship now, activated when those features land.
- External references:
  - MTEB: https://huggingface.co/spaces/mteb/leaderboard
  - BEIR: https://github.com/beir-cellar/beir
  - FEVER: https://fever.ai/
  - HaluEval: https://github.com/RUCAIBox/HaluEval
  - CLEF CheckThat!: https://checkthat.gitlab.io/
