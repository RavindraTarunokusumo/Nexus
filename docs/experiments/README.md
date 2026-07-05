# Experiments

Working log of benchmark-optimization experiments: hypotheses, the harness used,
raw variant comparisons, and conclusions (what shipped, what was rejected, what's
left). Distinct from `docs/benchmarks/` (formal reports for merged work) and
`docs/superpowers/specs|plans/` (spec-driven feature work) — this folder is the
lab notebook: fast, dated, evidence-first, and honest about ceilings.

Each experiment is a dated markdown file; bulky raw outputs go under `data/`.

## Index

- [2026-07-04 — LongMemEval answer-path optimization](2026-07-04-longmemeval-answer-path.md)
  — Chain-of-Note + lean prompt lift 0.692→0.834 at −37% tokens (answer-path only).
  Establishes the ~0.83 answer-path ceiling and the three retrieval-side "walls"
  blocking 0.90.
- [2026-07-05 — Ingestion token levers](2026-07-05-ingestion-token-levers.md)
  — the answer path is 3.4% of tokens; ranks the structural levers for the 96%
  (pre-LLM pair gate, batching, prefix caching, short-circuit) and the
  low-moderate-risk-only specification for fine-tuning.
