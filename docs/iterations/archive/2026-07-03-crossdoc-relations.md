# Cross-Document Relation Pass

**Branch:** `claude/crossdoc-relations`
**PR:** [#27](https://github.com/RavindraTarunokusumo/Nexus/pull/27)
**Merge commit:** `259df9b`
**Merged at:** 2026-07-03
**Merged by:** RavindraTarunokusumo

## Summary

Implemented the baseline report's top follow-up: a domain-wide relation pass that
classifies capsule pairs **across documents** — previously `classify_relations` only
paired capsules within one extraction run, so cross-doc `supersedes`/`contradicts`
edges never existed. The worker groups non-terminal capsules by `(object_family,
primary actor)`, pairs across documents only, dedups against existing rows
(idempotent), orders by document `published_at` (newer capsule = relation source, so
supersedes lands as an incoming edge on the older capsule — what the lifecycle check
consumes), and caps LLM calls at `max_pairs` (default 60). Surfaced as
`nexus relations run` and as a benchmark stage between extraction and lifecycle.

Spec: [`docs/superpowers/specs/2026-07-03-crossdoc-relations.md`](../../superpowers/specs/2026-07-03-crossdoc-relations.md) (including the Final T-X3 disposition)
Plan: [`docs/superpowers/plans/2026-07-03-crossdoc-relations.md`](../../superpowers/plans/2026-07-03-crossdoc-relations.md)

## Tasks Completed

- [x] Spec + plan + TODO sub-items. (`f83da01`)
- [x] T-X1 — `app/intelligence/cross_relations.py` worker + 13 unit tests (Grok
  implementer). (`9b4eff0`)
- [x] T-X2 — `nexus relations run` CLI + registration + benchmark stage + smoke tests
  (Grok implementer; 2 transient tool errors in its log, output intact). (`233b7b8`)
- [x] T-X3 run-1 finding — router `current_state` recency override buried past-dated
  capsules (recency input = ingestion order); override dropped, `factoid` classify
  definition covers past-event when-questions, runner records
  `question_shape`/`query_intent` per row. (`3089776`)
- [x] T-X3 run-2 finding — transient extraction network error left a doc at
  `claims_extracted` with zero capsules; runner now warns on zero-capsule docs.
  (`5dec513`)
- [x] T-X3 closed over 3 runs with the spec's Final T-X3 disposition (strict single-run
  gate unmet; every miss non-cross-doc; feature-positive: cross-doc supersedes edge
  correctly retired the nov-2025 pricing capsule, thesis 0.667/precision 0.792 run 1).
  (`5c6e0ed`)
- [x] `/simplify` (Grok) — `relations_created` became a computed field (counter-proposal
  to dropping the field: keeps the shipped JSON schema, removes divergence risk); single
  read session; SQL-level dedup filter; CLI wrapper inlined. Pushed back:
  `OrderedCapsulePair`→tuple (named fields document the direction contract);
  `session_factory`→`session` API (extraction-pass parity). (`e7e40d9`)
- [x] Security review (Grok) — no high-confidence findings (write envelope identical to
  per-doc pass, `max_pairs` caps spend, CLI inherits validated db-url/ORM patterns).
- [x] PR #27 bundled review (Grok, PENDING 4627668339; 1 bug / 4 suggestions / 2 nits) —
  fixed the `created_at` direction bug (pair direction now follows `published_at`;
  permuted-ingestion-order tests), `--domain` optional with pack default,
  `--skip-cross-doc` runner flag, corpus-scoped zero-capsule warning, lifecycle-filter
  statement test. Accepted-as-documented: per-pair commit semantics. Deferred:
  pair-attempt ledger/cursor. (`d5dc9f4`)

## Test Results

537 passed / 6 pre-existing failures (same environment-specific set as PR #26,
previously reproduced on clean `main`). ruff/format/mypy at baseline throughout.

Live validation: 3 full benchmark runs (`docs/benchmarks/runs/crossdoc-t-x3{,-run2,-run3}/`),
14–27 cross-doc relations created per run, 91–121 candidate pairs, idempotent dedup.
Category scores swung ±0.25 across identical-code runs — documented as a benchmark-design
finding (single runs at n=3–4 per category sit below the stochastic pipeline's noise
floor), with multi-run averaging logged as the fix.

## What This Session Did Not Do (backlog — all in TODO.md)

- Benchmark multi-run averaging (`--runs N`, per-category mean/stddev).
- Publication-date-based recency in `compute_hybrid_score`.
- Extraction retry / zero-capsule status for transient LLM failures.
- Cross-doc pair-attempt ledger/cursor (none-classified pairs re-sent on rerun).
- Shared relation-persist helper (dedup vs `extraction.py`, deferred until that file is
  next open).

## Workflow Notes

See `docs/insights.md`, session `crossdoc-relations (2026-07-03)`, for the workflow
retrospective.
