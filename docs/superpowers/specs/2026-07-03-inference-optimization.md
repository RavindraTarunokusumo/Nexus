# Spec Draft: Inference Latency & Token Optimization (H8)

**Date:** 2026-07-03
**Status:** Draft — for review; quick wins may land pre-deadline, distillation is a future spec.
**Evidence base:** live `agent_runs` aggregate from the LongMemEval runs (50 instances,
partial): 2.13M tokens / ~$0.30, **claim_extraction = 81% of tokens (357 calls, 1.72M)**,
classify_relation = 16% (199 calls); wall-clock dominated by strictly serial multi-second
API round-trips (~1.5–3 min/instance). Cost is a non-issue; latency and per-call waste
are the targets.

## Tier 0 — Quick wins (hours each; candidates to land pre-deadline)

### Q0. Disable default thinking mode on Qwen calls (**found 2026-07-04; landing immediately**)

Diagnosis: `agent_runs` showed completion tokens wildly exceeding useful output
(classify_relation: 445 prompt → 1,261 completion for ~60 tokens of JSON;
chat_classify_intent: 931 completion for two enums). qwen3 hybrid models have thinking
enabled by default on DashScope and the client never disabled it. Live A/B on real
Nexus calls (same outputs both sides): extraction 25.9s/3,935 completion → **7.1s/1,020**
(3.6×); relation classify 13.0s/1,598 → **1.1s/67** (12×). Fix: `complete_json` gains
`thinking: bool = False` and sends `enable_thinking` in the payload; no caller opts in
today (T3 judge/synthesis may later). This one flag dominates every other Tier-0 item
and reorders the priority table: Q0 first, then concurrency (Q2), whose relative gain
shrinks but still stacks.

### Q1. Per-task T2 model routing (cheaper model for classification tasks)

Extraction needs the strongest T2 (structured multi-field output). But
`classify_relation` (enum + strength + one-line rationale), `chat_classify_intent`
(two enums), and the judge-adjacent tasks are *simple classification* — prime
candidates for a turbo-class model. Mechanism: extend the model tier map from a single
`t2_model` to a per-run-type routing table (config default + pack override), e.g.:

```
t2_model: qwen3.6-flash            # default / extraction
t2_light_model: <turbo-class id>   # classify_relation, chat_classify_intent, chat shape
```

**Gate (G2 discipline, non-negotiable):** verify the exact cheaper model id live against
the DashScope-intl account before wiring anything — the G4 dead-model-id bug class.
Then A/B on the synthetic benchmark: relation quality (relation counts + thesis
formation + `superseded` category) must hold.

### Q2. Bounded concurrency for independent LLM calls

Everything today is `await`ed serially. Three independent-call sites can use
`asyncio.gather` under a semaphore (start at 4–6 concurrent; DashScope rate limits are
the ceiling):
- per-span extraction calls within a document,
- per-pair relation classification (per-doc pass and cross-doc pass),
- benchmark question answering (questions are independent given a built memory;
  LongMemEval instances additionally need isolation — see Q4).

Expected: 3–5× wall-clock reduction on extraction-heavy stages with zero token change.
Risk: rate-limit 429s → semaphore + existing retry path; budget counters
(`t2_calls_used`) must become concurrency-safe (they're plain ints in graph state).

### Q3. Output-token diet

- `classify_relation` returns a free-text `rationale` we only store — cap it ("one
  clause, max 15 words") in the prompt and set `max_tokens` on classification calls.
- Same for the judge's rationale.
Small per call, ×199+ calls per run. No architectural change.

## Tier 1 — Medium (a day each; post-deadline unless the demo needs them)

### M1. Span batching in extraction

357 calls each carry the same multi-KB static prefix (pack taxonomy, facet guidance).
Batch k spans per call (k≈4–6) with per-span keyed outputs: fewer calls, shared prefix
amortized. Expected 40–60% extraction-token cut. Touches the extraction graph +
output-parsing contract — needs its own spec + regression run.

### M2. Prompt-prefix caching

DashScope exposes context caching for Qwen models (OpenAI-compatible `cache` options —
verify current API surface). The extraction prompt's static prefix is identical across
all calls in a run: caching it would cut *billed* input tokens dramatically even
without batching. Investigate + benchmark; combines multiplicatively with M1.

### M3. Pre-extraction span filter

The salience policy currently filters *after* a T2 call (the LLM reads filler smalltalk
and decides it's noise — we pay to discard). A cheap pre-filter (length threshold +
greeting/boilerplate regex + optional embedding-similarity-to-telos gate, all local)
skips obviously-empty spans before any API call. Conversation sources are filler-heavy,
so this disproportionately helps the `conversation_v1` path.

### M4. Domain-scoped retrieval → safe instance parallelism

`_run_retrieve_capsules` has no domain filter today (single-tenant assumption). Adding
`SemanticCapsule.domain == pack.domain` to the retrieval WHERE clause is correct
multi-domain behavior on its own AND unlocks running benchmark instances concurrently
in one DB (each instance under a distinct domain instead of TRUNCATE isolation) —
turning the serial 1.5–3 min/instance into a semaphore-bounded pipeline.

## Tier 2 — Future spec: T2 distillation (fine-tune on collected traces)

**The data is already being collected.** Every T2 call lands in `agent_runs` with
`input_json` + `output_json` + downstream validation signals (capsules that survived
judging and lifecycle; relations above strength thresholds; benchmark-judged answers).
That is a free, continuously-growing distillation set from `qwen3.6-flash`.

Sketch:
1. **Export tool** (`nexus eval export-traces`): filter `agent_runs` to
   validated-successful calls per run_type; emit chat-format JSONL
   (system+user → assistant JSON). Quality filter is the crux: only outputs that passed
   Pydantic validation AND downstream acceptance (e.g. capsule not judged-rejected,
   relation strength ≥ 0.6, benchmark `autoeval_label = true` for answer traces).
2. **Target**: a small fine-tunable Qwen (Model Studio fine-tuning if the hackathon
   account/voucher covers it; otherwise LoRA on open Qwen3-4B/8B weights post-hackathon)
   per task family — extraction first (81% of spend), relation classification second.
3. **Evaluation**: the benchmarks we now have ARE the acceptance gate — synthetic +
   LongMemEval subsets, distilled-T2 vs flash-T2, quality-per-dollar curve.
4. **Data volume reality check**: hundreds of traces today, low thousands after full
   benchmark runs — thin for full fine-tuning, plausible for LoRA on narrow structured
   tasks. Framing either way: "Nexus distills its own cost curve from validated
   production traces" — strong Devpost narrative even as a roadmap slide.

**Pre-deadline recommendation:** do NOT rush the fine-tune itself (training + eval
cycles don't fit the remaining days safely). DO land the export tool if time permits —
it's small, it makes the data collection deliberate instead of incidental, and it makes
the roadmap claim concrete in the demo.

## Priority order

| # | Item | Effort | Token impact | Latency impact | Pre-deadline? |
|---|---|---|---|---|---|
| 1 | Q2 concurrency | S | — | 3–5× | yes, if a session frees up |
| 2 | Q1 per-task T2 routing | S (+G2 check) | ~16% of calls cheaper | mild | yes, same session as Q2 |
| 3 | Q3 output diet | XS | small | small | rides along |
| 4 | M2 prefix caching | M (investigate) | potentially large | — | investigate only |
| 5 | M1 span batching | M | 40–60% extraction | large | no |
| 6 | M3 pre-filter | M | conversation-heavy win | mild | no |
| 7 | M4 domain-scoped retrieval | M | — | benchmark-parallel | no |
| 8 | T2 distillation | L | step change | step change | export tool only |

## Constraints

- Every model-id claim verified live before wiring (G4 lesson).
- Every optimization gated on a synthetic-benchmark A/B (quality holds before speed
  ships); multi-run averaging (existing TODO) strengthens these gates.
- No architectural rewrites: all Tier 0/1 items are localized to call sites, prompts,
  or config.
