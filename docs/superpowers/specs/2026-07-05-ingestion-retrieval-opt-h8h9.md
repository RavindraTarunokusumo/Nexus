# Spec: Ingestion & Retrieval Optimization (H9c + H8 + H9b)

**Date:** 2026-07-05
**Status:** Draft — experiment-first; structural levers (Track A) gate on zero-accuracy-loss, retrieval-accuracy work (Track B) gates on full-benchmark re-runs.
**Session:** `claude/perf-h8h9`
**Evidence base:** [`docs/experiments/2026-07-04-longmemeval-answer-path.md`](../../experiments/2026-07-04-longmemeval-answer-path.md) (token accounting, the 3 walls) and [`docs/experiments/2026-07-05-ingestion-token-levers.md`](../../experiments/2026-07-05-ingestion-token-levers.md) (ranked ingestion levers). Prior H8 draft: [`2026-07-03-inference-optimization.md`](2026-07-03-inference-optimization.md) — this spec supersedes its Tier-1 (M1–M4) planning with an experiment-first order and folds in the H9c pair-gate.

## Problem

Measured end-to-end per-question cost on LongMemEval (n=211, from `agent_runs`) is
**~69k tok/q**, of which the answer path is **3.4%**. The cost is **building the
memory graph**: `claim_extraction` 56.9% (10.6 calls/q) and `classify_relation`
38.8% (51.7 calls/q). Separately, accuracy plateaus at **~0.83** on the answer
path; the residual to 0.90 is three **retrieval-side** walls. This spec targets
both: cut ingestion tokens with zero accuracy loss (Track A), then push retrieval
accuracy toward 0.90 (Track B).

## Method — experiment-first, extract-once/replay-many

Every lever lands behind a measurement, not a hunch. Two harnesses already exist
(`run_longmemeval.py --dump-context` builds a frozen retrieval cache;
`replay_answer.py` replays the answer path over it). This spec adds **offline,
read-only characterization** where possible (no product code, no LLM spend) before
any implementation:

- **Pair-gate characterization (E1, no product code):** after a small
  ingest+extract run populates a DB, enumerate same-`object_family` capsule pairs,
  compute embedding cosine (`1 - (a.embedding <=> b.embedding)`, pgvector), and
  label each pair positive iff a `semantic_relations` row exists. Small runs (few
  capsules/family) stay under `max_pairs`, so "no row" ⟺ "classifier said none".
  Yields the cosine ROC that sizes the gate threshold at a target recall.
- Structural levers (Track A) are then gated on the **synthetic** benchmark
  (`nexus eval memory run`) A/B: relation counts, thesis formation, and the
  `superseded` category must hold. Cheap, fast, no full LongMemEval re-run.
- Retrieval-accuracy levers (Track B) require **full LongMemEval re-runs** (the
  replay cache is a frozen retrieval snapshot and cannot test retrieval changes).

## Track A — Ingestion token/latency levers (zero accuracy risk, do first)

Ordered by ROI per the ingestion-levers note. Each is a localized change (call
site, prompt, or config) — no architectural rewrite.

### A1. Pre-LLM candidate-pair gate (H9c lever 1 — highest ROI)

**Requirement:** drop candidate capsule pairs unlikely to relate *before* the LLM
call. Pairs are already `object_family`-grouped; add an embedding-cosine floor (and
optionally an entity/actor-overlap check) so topically-distant same-family pairs
never reach the classifier. ~56% of pair calls currently return "none".

**Interfaces (Consumes/Produces):**
- `app/intelligence/extraction.py::_run_classify_relations` — after `pairs` is built
  (the family-grouped list, ~line 432) and before the budget slice, filter by
  `cosine(cap_a.embedding, cap_b.embedding) >= threshold`. Consumes capsule
  embeddings (already loaded on the ORM objects); produces a shorter `pairs` list.
- `app/intelligence/cross_relations.py::build_cross_document_pairs` (the
  `combinations` loop, ~line 102) — same cosine floor on cross-doc pairs.
- New config: `settings.relation_pair_cosine_floor: float` (default from E1;
  `0.0` = disabled = today's behavior) + optional pack override.
- Cosine helper: reuse existing embedding utilities if present; else a 3-line
  numpy/pgvector cosine. No new dependency.

**Success gate:** on the synthetic benchmark, relation count and `superseded`
category hold within noise while `classify_relation` calls/q drop (target
−50–70%). Threshold chosen at the E1 recall knee (keep ≥95% of true relations).

**Risk:** a too-high threshold drops real relations (recall loss → missed
supersession → wrong "current state" answers). Mitigated by the E1 ROC and the
synthetic A/B gate. Default-off until the gate passes.

### A2. Relation-pair batching (H8 M1)

**Requirement:** classify N candidate pairs per LLM call instead of one, with
per-pair keyed outputs. Collapses ~52 calls → a handful and stops re-sending the
system prompt N× (prompt tokens are ~87% of relation-stage cost).

**Interfaces:** batched prompt builder + a keyed response model (list of
`{pair_key, relation_type, strength, rationale}`); `classify_pair` becomes
`classify_batch`. Same persistence loop consumes the parsed results. Touches the
relation-classify prompt contract → needs its own regression run.

**Success gate:** synthetic A/B relation quality holds; tokens/q down; parse
failures near zero (keyed-output robustness is the main hazard).

**Risk:** batched-output parsing (one bad key voids the batch). Bound batch size
(k≈4–6) and fall back to per-pair on parse failure.

### A3. DashScope prefix caching (H8 M2)

**Requirement:** the extraction/relation system-prompt prefix is re-sent on all
~65 calls/instance; DashScope bills cached prefixes at a fraction. Enable context
caching on the `LLMClient` calls where the prefix is static.

**Interfaces:** `app/intelligence/llm_client.py::LLMClient.complete_json` — pass the
provider cache option; verify the current DashScope-intl API surface live (G4
model-id-class discipline: verify before wiring). No signature change for callers.

**Success gate:** billed prompt tokens drop on repeated-prefix stages; outputs
byte-identical (caching must not change results). Investigate-then-benchmark.

**Risk:** provider API surface may differ from OpenAI's `cache` param; if
unsupported, this is a no-op — verify first, low effort, low risk.

### A4. Pre-extraction span filter (H8 M3)

**Requirement:** skip obviously-empty spans (greetings, boilerplate, sub-threshold
length) *before* the extraction LLM call. Conversation sources are filler-heavy.

**Interfaces:** `app/intelligence/extraction.py::extract_spans` — a local pre-filter
(length threshold + greeting/boilerplate regex + optional embedding-similarity-to-
telos gate) before dispatch. Consumes span text + pack telos; produces a filtered
span list. Filtered spans recorded as skipped, not failed.

**Success gate:** extraction calls/q drop on `conversation_v1`; capsule count and
synthetic quality hold.

**Risk:** over-filtering drops a span that carried a real fact. Keep the filter
conservative (only obvious filler); log skips for audit.

### A5. Deterministic short-circuit (H9c lever 4)

**Requirement:** rule-decidable relations (e.g. supersession = same `object_family`
+ same actor + monotonic effective date) decided by heuristic; the LLM only sees
genuinely ambiguous pairs. Layers on top of A1's gate.

**Interfaces:** a pure classifier `try_rule_relation(cap_a, cap_b) -> RelationType |
None` consulted before the LLM in both classify loops. Reuses the existing
`effective_ts`/`_newer_older` cross-doc direction logic.

**Success gate:** rule-decided relations match the LLM's verdict on a held sample
(precision check) before it's allowed to skip the call.

**Risk:** a wrong rule persists a bad relation with no LLM check. Gate on the
precision sample; keep the rule set minimal and high-confidence.

## Track B — Retrieval accuracy for the 0.90 push (H9b, full re-runs, do after A)

The three walls from the answer-path experiment. Each needs full LongMemEval
re-runs; sequence after Track A so the cheaper ingestion wins land first.

### B1. Wall 1 — un-retrieved evidence (top-k / ranking)

Gold evidence sometimes never enters context (`cov≈0`); model correctly abstains.
**Interface:** `app/intelligence/chat.py` retrieval — raise fetch pool / effective
`top_k` for the affected shapes, or improve candidate ranking so gold survives the
cut. Gate: LongMemEval coverage (`cov`) up, no accuracy regression elsewhere.

### B2. Wall 2 — supersession-direction

Questions asking for the *superseded* value ("where did I **initially**…",
"**previous** best") while the pipeline prefers the current fact. **Interface:** a
question-shape / intent path that detects "initial/previous/original" and flips the
recency preference (retrieval weighting + answer-prompt hint). Ties into the H5
router (`app/intelligence/router.py`) and `compute_hybrid_score` recency. Gate:
`supersession_correctness` up without hurting current-state questions.

### B3. Wall 3 — ordering & counting (per-sub-query retrieval slots)

"How many X before Y" off-by-one — a qualifying comparand sits outside top-k. This
is the **corrected R2 design** (reverted in H7): allocate a per-sub-query retrieval
floor (`ceil(effective_top_k / (1 + len(sub_queries)))` guaranteed slots) before
any shared rerank, so one entity's sub-query can't starve the other. **Interface:**
`app/intelligence/chat.py` retrieval + `docs/superpowers/specs/2026-07-03-longmemeval-adapter.md`
Amendment 2. Gate: comparison/aggregation accuracy up, no global regression.

## Success criteria

- **Track A:** relation-stage tokens/q ~27k → <10k (per the levers note) and
  extraction tokens/q down, with synthetic-benchmark relation/thesis/`superseded`
  quality held within noise. Each lever independently A/B-gated and default-off
  until it passes.
- **Track B:** LongMemEval overall accuracy above the 0.834 answer-path ceiling,
  measured on full re-runs; per-wall category metrics (coverage,
  supersession_correctness, comparison) improve without net regression.

## Constraints

- Every model-id / provider-API claim verified live before wiring (G4 lesson).
- No architectural rewrites; all Track A items are localized to call sites,
  prompts, or config. New behavior default-off behind config until its gate passes.
- Experiments use small subsets (E1: ~10–15 instances; synthetic A/B) before any
  full LongMemEval run; provision worker DBs with schema (`alembic upgrade head`).
- Amortization caveat stands: ingestion cost is 96% of tokens *per write* but
  amortizes across reads in production — weight Track A vs B by the write/read mix.
- Distillation (H8 Tier 2) remains out of scope here: trace-export tool only, no
  fine-tune, per the ingestion-levers note's held-out-domain discipline.
