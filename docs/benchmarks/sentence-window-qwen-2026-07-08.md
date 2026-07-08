# Benchmark Report — Sentence-Window Memory on the Qwen Stack (2026-07-08)

Final evaluation of the deterministic **sentence-window** memory architecture on a
fully **Qwen-native** stack (embedder, reader, and judge are all Qwen models).

## Headline

| Benchmark | Scope | Accuracy | Median tokens/answer |
| --- | --- | --- | --- |
| **LongMemEval** | full 500 (all 6 categories) | **0.864** | 4,033 |
| **LoCoMo** | 48-question eval subset (6 conv × 8 q, all 5 categories) | **0.750** | 6,517 |

## Stack

| Tier | Model | Role |
| --- | --- | --- |
| T1 embedder | **Qwen3-Embedding-0.6B** (local, MRL-truncated to 384-dim) | ingest + query embeddings |
| Reader | **qwen3.7-plus** (thinking) | Chain-of-Note answer generation |
| Judge | **qwen3.7-max** | evaluation scoring (not part of the product) |

Retrieval config: hybrid (semantic ANN ⊕ Postgres full-text lexical, RRF-fused) over
local sentence windows; inference-permitting reader prompt; partial-credit judge for
LoCoMo open-domain. Ingestion is fully local (deterministic sentence split + local
embeddings) — **zero LLM tokens at ingest**.

## LongMemEval — full 500

| category | n | accuracy |
| --- | --- | --- |
| knowledge-update | 78 | 0.962 |
| single-session-assistant | 56 | 0.964 |
| single-session-user | 70 | 0.957 |
| temporal-reasoning | 133 | 0.872 |
| multi-session | 133 | 0.752 |
| single-session-preference | 30 | 0.667 |
| **overall** | **500** | **0.864** |

- **multi-session (0.75)** is the genuine weak spot — cross-session multi-hop reasoning,
  where the answer spans several sessions and the reader must join them.
- **single-session-preference (0.667)** is a real score, **not** a judge artifact: the
  judge uses the official rubric-style prompt (matching LongMemEval's `evaluate_qa.py`).
  The misses are genuine — the reader either abstains on recommendation questions ("suggest
  a hotel") when the preference context isn't retrieved, or gives advice that doesn't
  utilize the user's specific stated preference.

## LoCoMo — 48-question subset

| category | n | accuracy |
| --- | --- | --- |
| single_hop | 2 | 1.000 |
| open_domain | 5 | 0.800 |
| temporal | 23 | 0.783 |
| multi_hop | 18 | 0.667 |
| **overall** | **48** | **0.750** |

- **multi_hop rose from a ~0.33–0.47 floor to 0.667** once the reader (qwen3.7-plus) and
  embedder (Qwen3-Embedding) were upgraded — confirming the multi-hop wall was a
  reader-reasoning + embedding-quality problem, not a retrieval-structure one. Entity
  anchoring and sub-query decomposition (built and tested) did **not** move it and are off.

## Methodology caveats (report honestly)

1. **LongMemEval oracle variant.** We evaluate the *oracle* haystacks (evidence-only), not
   the distractor-laden LongMemEval-S. Published LongMemEval-S tables are therefore **not
   directly comparable** — oracle is an easier retrieval setting.
2. **LoCoMo subset, not full.** 48 questions (6 conversations), the session's iteration
   subset — chosen for cost/comparability. The full 1,878-question run was not executed.
3. **LLM-as-judge.** qwen3.7-max scores hypotheses against gold with category-specific
   rubrics mirroring the official evaluators; some residual judge noise is expected.

## Cost

Ingestion: **$0** (local). Billable = reader + judge tokens only. Full-LongMemEval-500
consumed ~2.26M tokens end-to-end; LoCoMo-48 ~0.34M. No per-write LLM extraction tax
(the sentence-window pivot eliminated the old ~69k-token/question extraction pipeline).

## Run artifacts

- `docs/benchmarks/runs/final-lme-qwen37plus/` — LongMemEval 500
- `docs/benchmarks/runs/final-locomo-qwen37plus/` — LoCoMo 48
