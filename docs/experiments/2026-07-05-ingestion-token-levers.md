# Ingestion Token Levers — Where the Real Cost Is (2026-07-05)

Forward-looking experimentation notes (not yet run). Companion to
[2026-07-04 answer-path optimization](2026-07-04-longmemeval-answer-path.md),
which established that the answer path is only **3.4%** of end-to-end tokens.
This note ranks the levers for the other **96%** — the ingestion pipeline — and
records where fine-tuning does and does not belong.

## The measured picture

End-to-end per-question cost (from `agent_runs`, n=211; full table in the
answer-path note):

| stage | calls/q | tokens/q | % |
| --- | --- | --- | --- |
| claim_extraction | 10.6 | 39,469 | 56.9% |
| classify_relation | 51.7 | 26,884 | 38.8% |
| chat_answer | 1.0 | 2,380 | 3.4% |
| everything else | — | ~633 | 0.9% |
| **TOTAL** | 65.3 | **≈69,366** | 100% |

Per instance (code-traced): 2.1 documents, 21.0 capsules, 22.6 persisted
relations. So the cost is not "answering a question" — it is **building the
memory graph** for that question's corpus.

**Amortization caveat (read first).** The ~69k is a benchmark artifact: each
LongMemEval instance ingests a *fresh* corpus to ask *one* question, charging the
entire one-time ingestion to a single query. In production you ingest once and
answer many queries, so per-query cost amortizes toward the ~2.4k answer call.
Weight ingestion vs answer-path work by the write-heavy/read-heavy mix. But
ingestion is 96% of tokens *whenever a write happens*, so it is still the first
place to cut for any write-heavy workload.

## Mechanism — why 65 calls to memorize one corpus

- **`classify_relation` — 51.7 calls/q (the sink).** Relations are classified
  **pairwise between capsules**, one LLM call per candidate pair — O(n²) over ~21
  capsules, bounded by `max_pairs`. Two loops feed it: within-doc
  (`extraction.py:464`, `classify_pair` over pairs) and cross-doc
  (`cross_relations.py:102`, `combinations(group_caps, 2)`). Only ~23 of ~52
  pairs survive as relations; the other ~56% classify to "no relation" but still
  cost a full call.
- **`claim_extraction` — 10.6 calls/q.** One `complete_json` per chunk
  (`extraction.py:315`), ~5 chunks × ~2.1 documents (session transcripts are long
  and get chunked).

## Ranked structural levers (zero accuracy risk — do these first)

None of these change *what* gets classified or extracted, only which work reaches
the model and how calls are packed. That is why they carry no overfitting or
generalization risk.

1. **Pre-LLM pair gate — cheapest, highest ROI.** ~56% of pair calls return "no
   relation." Filter candidate pairs *before* the model by cheap signal — T1
   embedding cosine, or shared `object_family` / entity overlap. Most capsule
   pairs are topically unrelated and never need an LLM. Est. **−50-70% classify
   calls** at near-zero recall loss. Pair with persisting negative attempts (cf.
   the deferred cross-doc pair-attempt ledger) so reruns skip known non-relations.
2. **Batching.** Send N candidate pairs (or N chunks) per call instead of one.
   52 calls → a handful, and it stops re-sending the system prompt 52× — cutting
   *prompt* tokens, which are ~87% of the relation-stage cost. Already scoped as
   H8 M1 (`docs/superpowers/specs/2026-07-03-inference-optimization.md`).
3. **DashScope prefix caching.** The extraction/relation system-prompt prefix is
   re-sent on all ~65 calls/instance; DashScope bills cached prefixes at a
   fraction. Near-zero effort, cuts token *cost* across every stage. H8 M2.
4. **Deterministic short-circuit.** Rule-decidable relations (e.g. supersession =
   same `object_family` + monotonic date) via heuristic; the LLM only sees
   genuinely ambiguous pairs.

Combined estimate: relation classification **~27k → <10k tok/q** with no accuracy
change. Extraction similarly benefits from batching + larger chunks + a span
pre-filter.

## Fine-tuning — low-moderate-risk specification only

Distillation is a **distant last resort**, considered only *after* the structural
levers land and *only* if measurement still shows a gap worth the robustness
trade. The overfitting risk is entirely a function of *what* is distilled:

- **HIGH risk — do NOT do:** fine-tune the *answer* model on benchmark Q→A pairs.
  That is teaching to the test — it memorizes LongMemEval's question shapes and
  the `conversation_v1` distribution and will not transfer.
- **LOW-MODERATE risk — the only sanctioned form:** distill a *single, narrow,
  schema-defined sub-task* — relation-classify (capsule pair → relation type) or
  extraction (chunk → capsules) — onto a smaller/cheaper model, under all of:
  1. **Task, not answers.** Train on the sub-task's input→output, never on
     question→final-answer.
  2. **Multi-domain traces.** Harvest validated `agent_runs` traces across several
     corpora/domains (AI-tech pack, conversation pack, others) — not LongMemEval
     alone — so the model learns the *task*, not one benchmark's distribution.
  3. **Held-out domain for validation.** Reserve an entire domain unseen in
     training; accept the distill only if it holds on the held-out domain, not
     just an in-distribution split.
  4. **Bounded scope.** Ship a **trace-export tool first** (already the repo's H8
     stance: "a trace-export tool for now, not the fine-tune"); the fine-tune is a
     separate, gated decision after the exporter proves the data is diverse enough.

Rationale: a narrow schema-defined task generalizes because its output space is
fixed (a relation-type label, a capsule schema), so a small model can learn it
from diverse examples without absorbing benchmark-specific answer patterns. The
residual risk ("moderate") is that even a scoped distill trades some robustness on
novel domains for cost — which is why it runs behind the zero-risk structural
levers and behind a held-out-domain gate, not instead of them.

## Suggested experiment order

1. Pre-LLM pair gate (lever 1) — measure classify-call reduction + relation recall
   vs the current pairwise baseline on a held instance set.
2. Batching + prefix caching (levers 2–3) — measure tokens/q, no accuracy change
   expected.
3. Deterministic short-circuit (lever 4).
4. Only if a gap remains: trace-export tool → multi-domain distill of
   relation-classify with a held-out-domain gate.
