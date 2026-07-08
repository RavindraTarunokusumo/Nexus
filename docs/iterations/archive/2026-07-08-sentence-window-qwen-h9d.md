# H9d — Sentence-Window Memory on the Qwen Stack

**Branch:** `claude/h9b-walls`
**PR:** [#32](https://github.com/RavindraTarunokusumo/Nexus/pull/32)
**Merge commit:** `d161d94`
**Merged at:** 2026-07-08T02:49:59Z
**Merged by:** RavindraTarunokusumo

## Summary

Pivoted the memory system from the LLM extraction + relation-classification pipeline
(~69k tokens/question at ingest) to a **deterministic sentence-window** architecture:
local sentence-split ingest (zero LLM tokens), hybrid semantic⊕lexical retrieval
(RRF) over local ±window spans, answered by a thinking Chain-of-Note reader. Landed
on a fully **Qwen-native** stack.

**Final benchmarks** (Qwen3-Embedding-0.6B@384 · qwen3.7-plus reader · qwen3.7-max
judge, hybrid): **LongMemEval-500 = 0.864**, **LoCoMo-48 = 0.750**. Report:
[`docs/benchmarks/sentence-window-qwen-2026-07-08.md`](../../benchmarks/sentence-window-qwen-2026-07-08.md).
Spec/plan: `docs/superpowers/{specs,plans}/2026-07-06-sentence-window-retrieval.md`,
`2026-07-07-entity-anchored-retrieval.md`.

## What landed (each subitem → commit)

- **Inference-permitting reader prompt** (flag-gated) — `3c21057`. LME +0.02, LoCoMo
  abstain 9→2; the strict Chain-of-Note prompt over-abstained on conversational corpora.
- **Hybrid retrieval (lexical⊕semantic RRF) + sub-query decomposition + partial-credit
  open-domain judge** — `d6afb05`. Hybrid lifted LoCoMo temporal 0.78→0.83; partial
  judge lifted open_domain 0.20→0.80.
- **Notes-as-list coercion** in `ChatAnswerOutput` — `f4b444d`. Thinking models
  (glm-5.2/qwen) sometimes emit `notes` as a JSON array; coerce rather than fail.
- **Spec/plan for entity-anchored retrieval + pivot log** — `a209efc`.
- **Entity-anchored retrieval (Rung 1, Grok-built)** — `af93ada`. Local NER (GLiNER)
  span tags + JSONB `?|` channel into RRF; GIN index (migration `0007`).
- **Qwen embedder** — `fc24e10`. Qwen3-Embedding-0.6B with asymmetric query/document
  prompts and MRL truncation to 384-dim (no schema migration; bge path unchanged).
- **Final benchmark report + TODO** — `a2f2013`.
- **Review fixes (PR #32 bundled review)** — `1667c62`. Post-retry `LLMSchemaError`
  now degrades to the error-shaped abstention in both `chat.py` and
  `answer_sentence_window` instead of aborting; idempotent `ingest_sentence_spans`.
- **Deferred review findings tracked** — `30a6202`.

## Key findings (the experiment trail)

- **The multi_hop wall was reader/embedding, not retrieval structure.** LoCoMo
  multi_hop sat at ~0.33–0.47 across every retrieval lever (hybrid, k-sweep, sub-query,
  entity anchoring). It jumped to 0.67 only when the reader (→qwen3.7-plus) and embedder
  (→Qwen3-Embedding) were upgraded. Entity anchoring lifted temporal/open_domain recall
  but did **not** move multi_hop — confirming the diagnosis and pre-empting Rung 2.
- **Sub-query decomposition backfired** (multi_hop 0.47→0.39 via RRF dilution) — built,
  measured, dropped (flag off).
- **LongMemEval and LoCoMo want opposite abstention behavior** — LME's adversarial
  questions reward strict abstention; LoCoMo's inference questions punish it. The
  inference-permitting prompt is a per-corpus flag.
- **single-session-preference (LME 0.667)** is a real score, not a judge artifact — the
  judge already uses the official rubric-style prompt.
- Deferred (backlog / post-hackathon): corpus-scoped retrieval, Rung 2 relation graph
  (deprioritized), reader distillation qwen3.7-plus→small local student, /simplify
  cleanups. Tracked in `TODO.md`.

## Caveats (carried into the report)

LongMemEval **oracle** variant (evidence-only haystacks) — not comparable to
distractor-haystack LongMemEval-S tables. LoCoMo is the **48-question subset**, not the
full 1,878. LLM-as-judge with category rubrics mirroring the official evaluators.
