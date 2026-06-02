# Phase A — Telos-Semantic Extraction Bridge

**Branch:** `claude/determined-noether-93dc4a`
**PR:** [#15](https://github.com/RavindraTarunokusumo/Nexus/pull/15)
**Merge commit:** _TBD — set after merge_
**Merged at:** _TBD_
**Merged by:** _TBD_

## Summary

Cut the production extraction pipeline over from claim-first extraction to the
v0.7 telos-aware semantic-object path, with the new semantic objects projected
back into the existing `claims` / `claim_evidence` tables. No schema migration
this phase — the `semantic_capsules` / `semantic_relations` tables are deferred
to Phase B.

The change brings the previously-dead `personal_ai_tech.yaml` configuration to
life: it is now a full v3 purpose-grammar pack with telos, 10 source-type
profiles, 10 semantic-object families (each carrying `object_types`,
`core_type_mapping`, `mvp_claim_type`, `required_fields`), salience policy,
facet policy, relation grammar, epistemic policy, T0–T4 routing,
per-source budgets, retention windows, retrieval intents, hybrid score weights,
context assembly, and an evaluation contract. A new Pydantic loader validates
it; a telos-aware prompt drives the per-segment LLM call; a projection layer
gates and translates the result into the legacy `Claim` shape with a
forward-compat `_v0_7` payload stashed under `entities_json` for Phase B
backfill.

Plan: [`docs/superpowers/plans/2026-05-30-telos-semantic-extraction-bridge.md`](../../superpowers/plans/2026-05-30-telos-semantic-extraction-bridge.md).
Test plan: [`docs/test-plan-phase-a-telos-semantic.md`](../../test-plan-phase-a-telos-semantic.md).

## Tasks Completed

**Setup**
- [x] **Plan + TODO** — Phase A implementation plan committed; A0–A9 task breakdown logged (commit: `179d2d6`)

**A0 — Spec onto branch**
- [x] Copy `2026-05-29-ai-domain-pack-extraction-scheme-design.md` from the unmerged `codex/ai-domain-extraction-spec` worktree into `docs/superpowers/specs/` on this branch; cross-link from `docs/specs/domain-packs.md` (commit: `dafc2b0`)

**A1 — Domain pack loader (Pydantic + YAML)**
- [x] `app/domain_packs/loader.py` — Pydantic v2 models for the v3 minimal-MVP contract (Metadata, Telos, SourceTypeProfile, SemanticObjectFamily incl. `mvp_claim_type`, SaliencePolicy, FacetPolicy, RelationGrammar, EpistemicPolicy, ModelRoutingPolicy, Budgets, RetentionPolicy, RetrievalPolicy, ContextAssembly, EvaluationContract). Cached `load_pack(pack_id)`. Tests: valid load, xfail-on-legacy-shape, missing-pack `FileNotFoundError`, schema-invalid `ValidationError`, cache identity (commit: `b63e2b9`)
- [x] Code-review fixes — `Field(default_factory=...)` for mutable defaults to match `app/evaluation/datasets.py`; type bare `dict` as `dict[str, Any]`; module docstring on `DomainPack`; `import copy` hoisted in tests (commit: `1a1d1e2`)

**A2 — Rewrite `personal_ai_tech.yaml` to v3 purpose grammar**
- [x] Replace 37-line MVP YAML with a full v3 pack: 10 source-type profiles, 10 semantic-object families, all v3 sections. Legacy top-level keys (`topics`, `claim_types`, `brief_sections`, `models`) preserved at the bottom via `DomainPack(extra="allow")`. Updated the xfail test to assert the v3 load (commit: `38b09db`)

**A3 — Semantic-object extraction schema**
- [x] Add `CoreType` (15-entry Literal), `EpistemicState`, `SemanticObject`, `SemanticExtractionOutput` to `app/intelligence/llm_client.py`. Legacy `ExtractedClaim` / `ExtractionOutput` preserved. Unit tests for validation edges, defaults, JSON round-trip, and back-compat of the legacy claim schema (commit: `921e767`)

**A4 — Telos-aware extraction prompt**
- [x] `app/intelligence/prompts/extract_semantic_objects.py` — `SYSTEM_PROMPT`, `build_user_prompt(segment_text, metadata, pack, source_type)`, `build_correction_prompt`. Injects pack-derived telos, applicable semantic-object families, salience rules, facet keys, per-segment budget, JSON example. 20 tests (commit: `47d89d6`)
- [x] Code-review fix — derive `_CORE_TYPES` and `_CLAIM_TYPES` from `CoreType` / `ClaimType` via `typing.get_args(...)` so the prompt vocabulary stays in sync with the schemas automatically (commit: `1e26735`)

**A5 — Projection layer**
- [x] `app/intelligence/projection.py` — `ProjectedClaim` dataclass, `validate_object` (family / object_type / `mvp_claim_type` consistency, source-refs non-empty), `enforce_budgets` (per-source + per-segment caps, salience-descending), `project` (facet split, `entities_json["_v0_7"]` + `_function` + `_domain_family` stash, `claim_type` from `mvp_claim_type`). 13 tests covering the MVP-projection table (commit: `41e026e`)
- [x] Polish — hoist `from collections import defaultdict` to module-level; comment the stash keys; clarify `enforce_budgets` docstring (application order: per-segment then per-source); module-level `__all__` (commit: `35d86a0`)

**A6 — Wire extraction graph to telos-aware path**
- [x] `app/intelligence/extraction.py` — `load_spans` loads `Source` + `DomainPack` and stashes them in graph state; `_extract_one_span` uses the A4 prompt + `SemanticExtractionOutput`; new `validate_and_project` graph node runs A5; `store_claims` writes from `ProjectedClaim`s. `make_extraction_graph` / `run_with_context` / `STATUS_*` API surface unchanged. Pack-driven `source_type` fallback via `pack.metadata.supported_source_types[0]`. `ExtractedClaim` / `ExtractionOutput` kept alive in `llm_client.py` because `app/evaluation/runner.py` still consumes the latter (commit: `a83b6be`)
- [x] Code-review fixes — defensive `if state.get("error"): return {}` guards on `validate_and_project` and `store_claims`; type `projected_claims: list[tuple[str, ProjectedClaim]]`; update extraction module docstring; refresh the legacy-schema comment in `llm_client.py` (commit: `a0dfaa5`)

**A7 — T2 judge scaffold (stretch)**
- [x] `app/intelligence/prompts/judge_semantic_object.py` — `SYSTEM_PROMPT`, `JudgeVerdict` schema (`evidence_sufficient`, `recommended_confidence`, `escalate`, `rationale`), `build_judge_prompt`. **No graph integration yet** — escalation has no home table until Phase B (commit: `e032b07`)
- [x] Log Phase B prerequisite — wire the judge prompt into the extraction graph once a relation/audit destination exists (commit: `f3830e9`)

**A8 — Eval compatibility regression**
- [x] `tests/intelligence/test_a6_projection_regression.py` — no-DB, no-LLM smoke that runs 5 hand-authored `SemanticObject`s through validate → enforce_budgets → project against the real pack, verifying the `_v0_7` / `_function` / `_domain_family` stash is preserved and budgets cap the output. `docs/architecture.md` gains a "Phase A — Dual extraction paths and eval compatibility contract" subsection documenting why `ExtractionOutput` / `ExtractedClaim` stay alive until the eval runner is ported in Phase B (commit: `edfbd90`)

**A9 — Pre-PR docs pass**
- [x] doc-updater subagent updates `docs/architecture.md`, `docs/specs/domain-packs.md`, `docs/specs/pipeline.md`, `docs/patterns.md`, `docs/testing.md`, `docs/cli.md` for the Phase A surface (commit: `4bbc99f`)

**Step 6 — Pre-PR gates**
- [x] **`/simplify`** — Seven cleanups: remove unreachable sentinel; extract `_fail()` helper for `load_spans` guards; drop unused `span_id` from `projected_claims`; pre-build pack prompt prefix once per source (O(spans × families) → O(1) per source); move `SALIENCE_THRESHOLD` into `SaliencePolicy.min_floor`; pack-driven `source_type` fallback via `metadata.supported_source_types[0]`; shared `build_correction_prompt` in `prompts/_shared.py` (commit: `fb4d9f2`)
- [x] **`doc-updater`** — already covered by A9
- [x] **`security-review` (justified)** — Identified one High finding (path traversal via `POST /sources` → `load_pack`); fixed via shared `app/api/_validation.py` + `load_pack` confinement + sanitized error message (commit: `9a424f8`)
- [x] **`test-plan-writer` (justified)** — Post-implementation test plan at `docs/test-plan-phase-a-telos-semantic.md`; verdict WARN. Surfaced a real `IndexError` edge case in `_resolve_pack_and_source_type` against an empty `supported_source_types` (commit: `7c945e7`)
- [x] **Test-plan follow-up** — Empty-list defensive branch added to `_resolve_pack_and_source_type` (commit: `d1e5cb6`)

**Workflow chore commits**
- [x] GitNexus index stats refreshed mid-session (commits: `a841e20`, `9db47c6`)

## Test Results

- 100+ tests passing locally across `tests/domain_packs/` and `tests/intelligence/`.
- Six new test files added: `test_loader.py`, `test_semantic_object_schema.py`, `test_extract_semantic_objects_prompt.py`, `test_projection.py`, `test_a6_projection_regression.py`, `test_judge_semantic_object_prompt.py`.
- `tests/test_sources.py` extended with traversal-rejection payloads.
- DB-integration tests in `tests/test_extraction_graph.py` and `tests/test_sources.py` exercise the full path in CI — blocked locally by a pre-existing `langgraph.checkpoint.postgres` env issue documented in `docs/insights.md`.
- Pre-commit: `mypy` (now passing after `session_memory.py` got committed during /simplify) and `pytest-fast` (still blocked by the env issue) — every commit on this branch used `SKIP=mypy,pytest-fast` or `SKIP=pytest-fast`, justified under Workflow Rule 6.

## Post-Merge Review Fixes (Copilot Code Review)

_TBD — set after Copilot completes its review and findings (if any) are addressed via `/receiving-code-review`._

## What Phase A Did Not Do (Phase B backlog)

- `semantic_capsules`, `capsule_segments`, `semantic_relations`, `theses`, `decision_artefacts` Alembic migration; dual-write from projection; backfill from the `_v0_7` stash.
- Port `app/evaluation/runner.py` to `SemanticExtractionOutput`; add object-level eval gold sets; retire `ExtractedClaim` / `ExtractionOutput`.
- Wire the A7 T2 judge prompt behind a feature flag once `semantic_relations` exists.
- Telos-aware retrieval (`hybrid_score_weights` from the pack) + query-intent classification.
- Lifecycle / consolidation workers; thesis synthesis.
- Ingestion-side detection of the v3 source-type profile (replace the `supported_source_types[0]` fallback in `_resolve_pack_and_source_type`).
- Isolated unit test for `_resolve_pack_and_source_type` (currently covered only end-to-end).
