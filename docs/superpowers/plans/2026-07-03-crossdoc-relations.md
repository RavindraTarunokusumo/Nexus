# Plan: Cross-Document Relation Pass

**Spec:** `docs/superpowers/specs/2026-07-03-crossdoc-relations.md`
**Branch:** `claude/crossdoc-relations` (worktree `.worktree/crossdoc`)

Two delegated tasks (sequential — T-X2 imports T-X1's function), then orchestrator-run
live benchmark validation.

## File structure

- `app/intelligence/cross_relations.py` — NEW. `CrossDocReport`,
  `classify_cross_document_relations`, private pair-generation helpers.
- `tests/intelligence/test_cross_relations.py` — NEW. Pure pair-generation unit tests +
  mocked-session worker tests.
- `app/cli/relations.py` — NEW. Typer sub-app `relations_app`, command `run`.
- `app/cli/main.py` — register `relations_app` (one `add_typer` line + import).
- `scripts/benchmarks/run_memory_benchmark.py` — insert the pass between extraction and
  lifecycle; record `cross_doc_relations` counts in `run_meta.json`.
- `tests/test_relations_cli.py` — NEW. CLI smoke test (`--help`, bad domain) following
  the pattern of the lifecycle/consolidation CLI tests.

## Task decomposition

### T-X1 — Worker module + unit tests

**Consumes:**
- `SemanticCapsule` / `SemanticRelation` ORM models (`app/db/models.py`)
- `build_relation_prompt(cap_a, cap_b, pack)`, `RelationClassification`
  (`app/intelligence/prompts/classify_relations.py`)
- `_CANONICAL_RELATION_TYPES` (`app/intelligence/extraction.py`, import-only)
- `_primary_actor(facets)` (`app/intelligence/lifecycle.py`, import-only)
- `client.complete_json(model, system, user, response_model, run_type)` — use
  `run_type="classify_relation"` (same as per-doc pass)

**Produces:**
- `classify_cross_document_relations(session_factory, client, *, domain, pack, model,
  max_pairs=60, dry_run=False) -> CrossDocReport` per the spec's workflow section:
  non-terminal states filter, (family, actor) grouping with actor-None exclusion,
  cross-document-only pairs, existing-row dedup (either direction, capsule↔capsule rows
  only), deterministic newer-first ordering + cap, per-pair classify-and-persist with
  canonical/domain relation-type split identical to the per-doc pass, LLM-error
  continue, dry_run classifies nothing.
- Pair-generation helpers pure/module-level so unit tests don't need the LLM.

### T-X2 — CLI + benchmark wiring + smoke tests

**Consumes:** T-X1's `classify_cross_document_relations` + `CrossDocReport`;
`app/cli/lifecycle.py` as the structural template (including `_run()` and `--db-url`);
`run_memory_benchmark.py`'s existing stage sequence and `run_meta.json` assembly.

**Produces:**
- `nexus relations run` with `--domain` (required), `--pack`, `--max-pairs`, `--model`,
  `--dry-run`, `--json`, `--db-url`. JSON mode must always print the report object
  (avoid the known `lifecycle run --json` empty-output defect).
- Benchmark stage: after `_extract_new_documents`, before `apply_lifecycle_transitions`;
  reuses the runner's existing client/pack/model resolution; counts into `run_meta.json`.

**Boundaries (both tasks):** no git operations; no edits to `extraction.py`,
`lifecycle.py`, `theses.py`, pack YAMLs, or DB schema. Full-suite self-check
(`ruff check`, `ruff format --check`, `mypy app/`, `pytest`) before reporting; 6
pre-existing failures expected (loader abs-path, chat-api 503, 4 extraction/dual-write
mocks); single trailing newline per file.

### T-X3 — Live benchmark validation (orchestrator, not delegated)

Fresh scratch DB, full `run_memory_benchmark` run, gate on spec success criteria 3.
Compare relation counts and `multi_doc`/`superseded`/`thesis` vs `router-t-r2`.

## Build order

T-X1 → orchestrator gate + commit → T-X2 → orchestrator gate + commit → T-X3 →
(tuning commit if needed) → Submit PR flow.

## Risks

- **Pair explosion despite grouping** — actor facet quality decides candidate count; the
  cap (`max_pairs=60`) is the hard bound. If the synthetic corpus yields too few pairs
  (over-strict actor match), the benchmark won't move — the report's `candidate_pairs`
  count is the diagnostic.
- **Duplicate edges vs per-doc pass** — same-doc pairs are excluded by construction and
  existing-row dedup covers reruns, but the per-doc pass runs first in the benchmark;
  ordering is load-bearing. The runner change enforces it.
- **Direction errors** — lifecycle `_check_superseded_relation` fires on *incoming*
  supersedes; newer-first (A=newer) must be verified by a unit test asserting source/target
  assignment from `created_at`.
