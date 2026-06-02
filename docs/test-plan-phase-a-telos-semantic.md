# Test Plan — Phase A: Telos-Semantic Extraction Bridge

| Field | Value |
|---|---|
| **VERDICT** | WARN |
| **MERGE_BLOCKING** | no |
| **Date** | 2026-05-31 |
| **Branch** | `claude/determined-noether-93dc4a` |
| **Diff base** | `fbda9a7..HEAD` |
| **Author** | test-plan-writer subagent |

**Verdict rationale:** All P0 and most P1 cases are covered by the Phase A test suite. The
significant gap is the full extraction graph integration path (`test_extraction_graph.py`),
which requires a real testcontainers PostgreSQL database and cannot execute in the local dev
environment due to the `langgraph.checkpoint.postgres` import chain in `tests/conftest.py`
(pre-existing env issue). Those tests exist and are correct; they are CI-only. Two additional
P1 gaps exist: no unit test for `_resolve_pack_and_source_type` returning
`pack.metadata.supported_source_types[0]` in isolation, and no negative test for an empty
`supported_source_types` list. Both are low-risk given the integration graph tests, but they
are documented as follow-up gaps.

---

## 1. Summary

Phase A delivers the Telos-Semantic Extraction Bridge: a v0.7 domain-pack–driven extraction
pipeline that replaces the legacy `ExtractedClaim` / `ExtractionOutput` production path with a
`SemanticObject` → `ProjectedClaim` → DB flow. Key additions are:

- A typed Pydantic v3 domain-pack loader (`app/domain_packs/loader.py`) with LRU cache and
  path-traversal hardening.
- A full v3 `personal_ai_tech.yaml` pack covering 10 semantic families.
- New v0.7 schema types in `llm_client.py`: `CoreType`, `EpistemicState`, `SemanticObject`,
  `SemanticExtractionOutput`.
- A projection layer (`projection.py`): `validate_object`, `project`, `enforce_budgets`.
- A telos-aware extraction prompt with cached source-prefix split
  (`prompts/extract_semantic_objects.py`, `prompts/_shared.py`).
- A scaffolded T2 judge prompt (`prompts/judge_semantic_object.py`) — not yet wired to the
  extraction graph.
- A `validate_and_project` graph node in `extraction.py` that replaces the legacy path.
- Shared API identifier validation (`app/api/_validation.py`) used on `POST /sources` and
  ingestion routes.

Legacy `ExtractedClaim` / `ExtractionOutput` are preserved for the eval runner.

---

## 2. Scope

### In scope

- Domain-pack loader: loading, caching, schema validation, path-traversal rejection.
- v0.7 schema types: field constraints, defaults, round-trips.
- Projection layer: `validate_object` gates, `project` key stash, `enforce_budgets` caps.
- Extraction prompt: content, cached-prefix equality, correction-prompt shape.
- Judge prompt scaffold: shape and schema — not graph integration.
- Extraction graph: semantic path, `validate_and_project` node, error state guards (CI-only).
- API security: `validate_identifier` regex, `POST /sources` rejection of traversal IDs.
- Back-compat: `ExtractedClaim` / `ExtractionOutput` still parse.
- Pack YAML: legacy top-level keys preserved; all 11 `ClaimType` values projected.

### Out of scope

- Phase B graph wiring for the T2 judge (escalation table does not exist yet).
- Eval framework changes (none made; `app/evaluation/` untouched).
- T3/T4 routing, cross-source contradiction resolution, Phase B backfill of `_v0_7`.

---

## 3. Environment constraints

| Category | Status |
|---|---|
| Pure unit/integration tests (no DB) | Runnable locally with `--noconftest` |
| DB integration tests (`test_extraction_graph.py`, `test_sources.py`, others using `client` fixture) | **CI-only** — `tests/conftest.py` imports `langgraph.checkpoint.postgres` which is not installed locally |
| OpenRouter / LLM calls | None — all graph tests use `FakeLLMClient` |

Run command for local (no-DB) tests:
```
python -m pytest tests/intelligence/ tests/domain_packs/ -v --noconftest
```

---

## 4. Coverage Mapping

| Acceptance Criterion | Test IDs | Status |
|---|---|---|
| AC-1: Telos-aware extraction — per-span LLM call uses v0.7 prompt, returns `SemanticExtractionOutput` | EG-1, EG-2 | Covered (CI-only) |
| AC-2: Projection — `SemanticObject` → `Claim` + `ClaimEvidence` with `_v0_7`, `_function`, `_domain_family` keys | PR-1, EG-5, A8-4, A8-5 | Covered |
| AC-3: Budgets — `enforce_budgets` caps per-source and per-segment, salience-descending | PR-5, PR-6, PR-7, A8-6 | Covered |
| AC-4: Validation gates — family/object_type/`mvp_claim_type` consistency; salience-floor rejection | PR-2, PR-3, PR-4 | Covered |
| AC-5: Schema/back-compat — legacy `ExtractedClaim` / `ExtractionOutput` parse unchanged | SC-3 | Covered |
| AC-6: Pack-driven `source_type` fallback — `supported_source_types[0]` first | EG-1 (implicit); no isolated unit test | **Gap (P1)** |
| AC-7: API surface preserved — `make_extraction_graph`, `run_with_context`, `STATUS_*` unchanged | EG-1 through EG-6 | Covered (CI-only) |
| AC-8: Security — `domain_pack` regex on `POST /sources`; `load_pack` path-traversal; no absolute-path leak | LP-5, LP-6, LP-7, SRC-1 | Covered |
| AC-9: Eval contract — `ExtractionOutput` remains SUT response type; `app/evaluation/` untouched | SC-3 | Covered |

---

## 5. Test Cases

### 5.1 Pack Loader (`tests/domain_packs/test_loader.py`)

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| LP-1 | P1 | `TestLoadValidPack::test_required_fields_parse` | Valid minimal pack loads; `metadata.pack_id` and `telos.primary_purposes` correct | **Implemented** |
| LP-2 | P1 | `TestLoadValidPack::test_defaults_applied` | All optional fields (budgets, facet_policy, salience_policy, etc.) receive correct defaults | **Implemented** |
| LP-3 | P2 | `TestLoadValidPack::test_semantic_family_mvp_claim_type` | `mvp_claim_type` dict accessible per family | **Implemented** |
| LP-4 | P2 | `TestLoadValidPack::test_extra_top_level_keys_allowed` | `extra="allow"` means legacy YAML keys do not raise `ValidationError` | **Implemented** |
| LP-5 | P0 | `TestLoadPackRejectsPathTraversal::test_traversal_raises_file_not_found[../etc/passwd]` | Traversal ID raises `FileNotFoundError`; message does not leak absolute path | **Implemented** |
| LP-5b | P0 | `TestLoadPackRejectsPathTraversal::test_traversal_raises_file_not_found[..\\foo]` | Windows-style traversal also rejected | **Implemented** |
| LP-5c | P0 | `TestLoadPackRejectsPathTraversal::test_traversal_raises_file_not_found[a/../b]` | Embedded `..` traversal rejected | **Implemented** |
| LP-6 | P0 | `TestLoadPackRejectsPathTraversal::test_absolute_path_raises_file_not_found` | Absolute path ID rejected; no absolute-path leak in error message | **Implemented** |
| LP-7 | P0 | `TestMissingPackRaisesFileNotFoundError::test_raises_file_not_found` | Missing pack ID raises `FileNotFoundError`; `tmp_path` not in message | **Implemented** |
| LP-8 | P1 | `TestSaliencePolicyMinFloor::test_default_min_floor` | Default `min_floor` is 0.3 | **Implemented** |
| LP-9 | P1 | `TestSaliencePolicyMinFloor::test_custom_min_floor_from_yaml` | Custom `min_floor: 0.5` from YAML respected | **Implemented** |
| LP-10 | P1 | `TestInvalidPackRaisesValidationError::test_missing_required_field_raises` | Missing `pack_id` raises `ValidationError` | **Implemented** |
| LP-11 | P1 | `TestCacheHit::test_same_object_identity` | Two `load_pack` calls return same object (LRU cache) | **Implemented** |
| LP-12 | P1 | `TestCacheHit::test_clear_cache_forces_reload` | `clear_cache()` forces re-read from disk | **Implemented** |
| LP-13 | P2 | `test_personal_ai_tech_yaml_loads_as_v3` | Full `personal_ai_tech.yaml` loads; 10 families; all 11 `ClaimType` values projected; legacy YAML keys present | **Implemented** |
| LP-14 | P1 | *(gap)* `test_load_pack_source_type_fallback_first_entry` | `_resolve_pack_and_source_type` returns `pack.metadata.supported_source_types[0]` | **Gap — follow-up** |
| LP-15 | P1 | *(gap)* `test_load_pack_source_type_fallback_empty_list` | `supported_source_types: []` triggers safe fallback / does not index-error | **Gap — follow-up** |

### 5.2 v0.7 Schema Types (`tests/intelligence/test_semantic_object_schema.py`)

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| SC-1 | P1 | `test_valid_minimal_semantic_object` | Minimal `SemanticObject` parses; optional-field defaults apply | **Implemented** |
| SC-2 | P1 | `test_source_refs_empty_rejected` | `source_refs: []` raises `ValidationError` | **Implemented** |
| SC-2b | P1 | `test_invalid_core_type_rejected` | `core_type` outside 15-literal vocab rejected | **Implemented** |
| SC-2c | P1 | `test_invalid_mvp_claim_type_rejected` | `mvp_claim_type` outside 11-literal vocab rejected | **Implemented** |
| SC-2d | P1 | `test_confidence_out_of_range` (parametrize -0.1, 1.5) | `confidence` bounds enforced by `EpistemicState` | **Implemented** |
| SC-2e | P1 | `test_salience_out_of_range` (parametrize -0.1, 1.5) | `salience` bounds enforced by `SemanticObject` | **Implemented** |
| SC-2f | P1 | `test_epistemic_state_defaults` | `EpistemicState` defaults (`unknown` authority, `unknown` quality, etc.) | **Implemented** |
| SC-3 | P0 | `test_legacy_extraction_output_still_parses` | `ExtractedClaim` + `ExtractionOutput` parse unchanged; `claim_type` and `confidence` correct | **Implemented** |
| SC-4 | P1 | `test_semantic_extraction_output_round_trip` | `SemanticExtractionOutput` JSON round-trip preserves two objects | **Implemented** |

### 5.3 Projection Layer (`tests/intelligence/test_projection.py`, `tests/intelligence/test_a6_projection_regression.py`)

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| PR-1 | P0 | `test_happy_path_validate_and_project` | Accepted object produces `ProjectedClaim`; `_v0_7` == `obj.model_dump(mode="json")`; `_function` and `_domain_family` present; `domain_terms` + `unknown_salient_terms` routed to `topics_json` | **Implemented** |
| PR-2 | P1 | `test_salience_gate_rejected` | `salience < pack.min_floor` → rejected; reason mentions salience floor value | **Implemented** |
| PR-3 | P1 | `test_unknown_family_rejected` | Unknown `domain_family` → rejected with family name in reason | **Implemented** |
| PR-4 | P1 | `test_unknown_object_type_rejected` | `domain_object_type` not in family → rejected with type name in reason | **Implemented** |
| PR-4b | P1 | `test_mvp_claim_type_mismatch_rejected` | Wrong `mvp_claim_type` → rejected; expected and got values in reason | **Implemented** |
| PR-5 | P1 | `test_facet_split` | Entity-like facets in `entities_json`; topic-like (`domain_terms`, `unknown_salient_terms`) merged into `topics_json["domain_terms"]` | **Implemented** |
| PR-6 | P1 | `test_mvp_projection_table` (4 parametrize cases) | `evaluation_evidence/benchmark_result`, `economics_pricing/funding_round`, `safety_security/security_vulnerability`, `forecast_outlook/capability_forecast` all pass validate → project | **Implemented** |
| PR-7 | P1 | `test_budget_per_source_cap` | 50 objects, patched cap 40 → 40 returned; top-salience order preserved | **Implemented** |
| PR-7b | P1 | `test_budget_per_source_type_override` | `source_type="ai_news_article"` → cap 12 applied from pack's `per_source_type` | **Implemented** |
| PR-7c | P1 | `test_budget_per_segment_cap` | 10 objects on same segment, segment cap 5 → 5 returned | **Implemented** |

#### A8 Regression Smoke (`tests/intelligence/test_a6_projection_regression.py`)

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| A8-1 | P1 | `test_fixture_objects_validate_against_schema` | All 5 fixture objects re-validate against `SemanticObject` (schema-drift guard) | **Implemented** |
| A8-2 | P0 | `test_all_five_objects_accepted_by_validator` | All 5 representative objects accepted by `validate_object` | **Implemented** |
| A8-3 | P0 | `test_all_five_objects_project_to_correct_claim_types` | Full pipeline produces `[model_release, benchmark_result, funding_event, security_issue, forecast]` | **Implemented** |
| A8-4 | P1 | `test_claim_type_matches_pack_mvp_table` (5 parametrize) | Cross-check fixture claim types against YAML pack table to catch pack drift | **Implemented** |
| A8-5 | P0 | `test_forward_compat_stash_keys_present` | Every projected claim carries `_v0_7`, `_function`, `_domain_family` in `entities_json` | **Implemented** |
| A8-5b | P0 | `test_forward_compat_stash_values_correct` | Stash values match source object fields exactly; `_v0_7 == obj.model_dump(mode="json")` | **Implemented** |
| A8-6 | P1 | `test_budget_caps_output` | 50 funding objects, patched cap 10 → 10 returned; top-salience objects survive | **Implemented** |

### 5.4 Extraction Prompt (`tests/intelligence/test_extract_semantic_objects_prompt.py`)

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| EP-1 | P1 | `test_system_prompt_is_nonempty_string` | `SYSTEM_PROMPT` is a non-empty string | **Implemented** |
| EP-2 | P1 | `test_system_prompt_mentions_semantic` | Mentions "semantic" | **Implemented** |
| EP-3 | P1 | `test_system_prompt_mentions_json` | Mentions "JSON" | **Implemented** |
| EP-4 | P1 | `test_prompt_contains_primary_purposes` | Telos primary purposes appear verbatim in user prompt | **Implemented** |
| EP-5 | P1 | `test_prompt_contains_anti_purposes` | Telos anti-purposes appear verbatim | **Implemented** |
| EP-6 | P1 | `test_prompt_contains_segment_text` | Segment text appears verbatim | **Implemented** |
| EP-7 | P1 | `test_prompt_contains_segment_id` | `segment_id` appears verbatim (provenance) | **Implemented** |
| EP-8 | P1 | `test_prompt_contains_budget_number` | `max_semantic_objects_per_segment` appears in "Do not emit more than N objects" | **Implemented** |
| EP-9 | P1 | `test_prompt_contains_applicable_family_names_when_profile_set` | Profile-filtered families appear; non-applicable excluded | **Implemented** |
| EP-10 | P1 | `test_prompt_contains_all_families_when_no_profile` | Fallback to all families when no matching profile | **Implemented** |
| EP-11 | P1 | `test_prompt_contains_salience_preserve_if` / `test_prompt_contains_salience_ignore_if` | Salience policy rules injected | **Implemented** |
| EP-12 | P1 | `test_prompt_contains_metadata_title_and_source` | Optional metadata fields injected when present | **Implemented** |
| EP-13 | P1 | `test_prompt_omits_absent_optional_metadata` | Absent metadata labels not emitted | **Implemented** |
| EP-14 | P1 | `test_missing_segment_id_raises_value_error` | Missing `metadata["segment_id"]` raises `ValueError` | **Implemented** |
| EP-15 | P1 | `test_prebuilt_prefix_equals_inline_build` | Pre-built `source_prefix` from `build_source_prompt_prefix` produces byte-identical prompt to inline build (caching correctness) | **Implemented** |
| EP-16 | P1 | `test_build_user_prompt_is_deterministic` | Two calls with same args produce identical string | **Implemented** |
| EP-17 | P2 | `test_correction_prompt_includes_original_user` / `_includes_invalid_response` / `_includes_error` | `build_correction_prompt` delegates to `_shared.build_correction_prompt`; all three parts present | **Implemented** |

### 5.5 Judge Prompt Scaffold (`tests/intelligence/test_judge_semantic_object_prompt.py`)

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| JP-1 | P1 | `test_system_prompt_is_nonempty` / `_mentions_evidence` / `_mentions_json` | `SYSTEM_PROMPT` shape | **Implemented** |
| JP-2 | P1 | `test_judge_verdict_valid_payload` | `JudgeVerdict` parses; fields accessible | **Implemented** |
| JP-3 | P1 | `test_judge_verdict_rejects_confidence_above_one` / `_below_zero` | Confidence bounds enforced | **Implemented** |
| JP-4 | P1 | `test_prompt_includes_object_text` / `_function` / `_pack_id` | Core object fields injected into judge prompt | **Implemented** |
| JP-5 | P1 | `test_prompt_includes_family_status_rules_when_present` / `_escalation_policy_when_present` | Epistemic rules section injected when family rules exist | **Implemented** |
| JP-6 | P1 | `test_prompt_omits_epistemic_rules_section_when_absent` | "Family-Specific Epistemic Rules" header absent when no rules | **Implemented** |
| JP-7 | P1 | `test_build_judge_prompt_is_deterministic` | Determinism | **Implemented** |

> **Note:** Judge prompt is scaffolded only. No extraction graph integration test for the judge
> is expected until Phase B wires it in.

### 5.6 Extraction Graph — DB Integration (`tests/test_extraction_graph.py`) — CI-only

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| EG-1 | P0 | `test_happy_path_stores_claims` | Full graph with 2 spans: `SemanticExtractionOutput` parsed; 2 `Claim` rows written; each carries `_v0_7`, `_function`, `_domain_family` in `entities_json`; 2 `ClaimEvidence` rows with `evidence_role="support"` | **Implemented (CI-only)** |
| EG-2 | P1 | `test_network_error_marks_document_failed` | `LLMNetworkError` aborts graph; document status `extraction_failed` | **Implemented (CI-only)** |
| EG-3 | P1 | `test_schema_error_retried_then_succeeds` | First call raises `LLMSchemaError`; correction-prompt retry succeeds; `len(client.calls) == 2` | **Implemented (CI-only)** |
| EG-4 | P1 | `test_all_retries_exhausted_marks_failed` | Three consecutive schema errors → `extraction_failed`; 0 claims | **Implemented (CI-only)** |
| EG-5 | P1 | `test_partial_extraction_status` | One span fails all retries, second succeeds → `extraction_partial`; 1 claim | **Implemented (CI-only)** |
| EG-5b | P1 | `test_extraction_populates_span_extractions_table` | `span_extractions` rows populated with `run_id`, `document_id`, `status="success"` | **Implemented (CI-only)** |
| EG-5c | P1 | `test_extraction_populates_document_timestamps` | `extraction_started_at` and `extraction_completed_at` set; completed >= started | **Implemented (CI-only)** |
| EG-6 | P0 | `test_claim_has_v07_traceability_keys` | `entities_json["_domain_family"] == "model_system"`, `_function` not None, `_v0_7["domain_object_type"] == "model_release"` | **Implemented (CI-only)** |

### 5.7 API Security — `POST /sources` (`tests/test_sources.py`) — CI-only

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| SRC-1 | P0 | `test_create_source_rejects_traversal_domain_pack` (5 parametrize cases) | `domain_pack` values failing `^[a-z0-9_\-]{1,64}$` return HTTP 422; `"domain_pack"` in error detail | **Implemented (CI-only)** |
| SRC-2 | P1 | `test_create_source_rss` | Valid `domain_pack="personal_ai_tech"` accepted; HTTP 201 | **Implemented (CI-only)** |

---

## 6. Edge Cases and Negative Tests

| ID | Priority | Description | Status |
|---|---|---|---|
| NEG-1 | P0 | `load_pack("../etc/passwd")` raises `FileNotFoundError` with no absolute path leak | **Implemented** (LP-5) |
| NEG-2 | P0 | `load_pack` of absolute path string (e.g. full OS path) raises `FileNotFoundError` | **Implemented** (LP-6) |
| NEG-3 | P0 | `ExtractionOutput(claims=[...])` still parses after v0.7 schema additions | **Implemented** (SC-3) |
| NEG-4 | P1 | `validate_object` with `source_refs=[]` → rejected ("source_refs is empty") | Covered implicitly by `SemanticObject` validator (SC-2); explicit `validate_object` path not independently tested — **minor gap** |
| NEG-5 | P1 | `validate_object` with `salience=0.0` (below any realistic `min_floor`) → rejected | **Implemented** (PR-2 covers salience=0.1 < 0.3 floor) |
| NEG-6 | P1 | `enforce_budgets` with zero objects → returns empty list | Not explicitly tested — **minor gap** |
| NEG-7 | P1 | `enforce_budgets` with `source_type` matching `per_source_type` takes min of global and type cap | **Implemented** (PR-7b covers `ai_news_article` cap=12 < global cap=80) |
| NEG-8 | P2 | Per-segment cap interacts with per-source cap correctly when both are binding | **Implemented** (PR-7 covers per-source; PR-7c covers per-segment; interaction tested separately but not in a combined binding case — **minor gap**) |
| NEG-9 | P2 | `build_user_prompt` without `source_prefix` and without `(pack, source_type)` raises `ValueError` | Covered by existing test behaviour (`test_missing_segment_id_raises_value_error` tests related guard) — implicit; no dedicated test |
| NEG-10 | P2 | `build_correction_prompt` in `extract_semantic_objects.py` delegates to `_shared.build_correction_prompt` with `schema_name="SemanticExtractionOutput"` | **Implemented** (EP-17 checks all three content sections; schema name verifiable from source) |
| NEG-11 | P1 | `POST /sources` with `domain_pack` > 64 characters returns HTTP 422 | **Implemented** (SRC-1 parametrize case `"valid_but_" + "x" * 60`) |
| NEG-12 | P1 | `POST /sources` with `domain_pack` containing uppercase returns HTTP 422 | Not explicitly parametrized — **minor gap** |

---

## 7. Fixtures and Setup Requirements

### Local (no DB, `--noconftest`)

- No additional setup required.
- Tests self-contain pack fixtures using `monkeypatch` on `_pack_dir` and `tmp_path`.
- `test_a6_projection_regression.py` depends on `tests/fixtures/a8_projection_input.json` — must be present (it is checked in).
- `test_projection.py` and `test_a6_projection_regression.py` call `load_pack("personal_ai_tech")` directly from the real YAML on disk.

### CI (DB-required)

- `tests/conftest.py` spins up a testcontainer PostgreSQL via `pytest-asyncio` + `testcontainers`.
- `test_extraction_graph.py` requires `session_factory` and `db_url` fixtures from `conftest.py`.
- `test_sources.py` requires the `client: AsyncClient` fixture from `conftest.py` (full FastAPI app).
- `SKIP=mypy,pytest-fast` skips type checking and the fast-test subset when running pre-commit.

### Cache hygiene

- `tests/domain_packs/test_loader.py` uses an `autouse` fixture (`_clear_loader_cache`) that calls `clear_cache()` before and after each test. Tests in `test_projection.py` and `test_a6_projection_regression.py` load the real pack at module level — acceptable since those are read-only.

---

## 8. Out of Scope

| Area | Reason |
|---|---|
| T2 judge graph wiring | Explicitly deferred to Phase B; no escalation table exists. |
| T3 / T4 routing | Not implemented in Phase A. |
| Cross-source contradiction detection | Phase B concern. |
| `app/evaluation/` | No changes made; eval runner uses legacy `ExtractionOutput`. |
| `_shared.build_correction_prompt` as a unit on its own | Covered transitively via `extract_semantic_objects.build_correction_prompt` tests (EP-17). |
| `app/intelligence/session_memory.py` | Touched in the diff but the change is unrelated to the semantic bridge (no functional modification). |
| `routes_ingestion.py` `validate_identifier` usage | Two call sites exist; functional coverage relies on CI integration tests for ingestion routes. |

---

## 9. Open Questions

| # | Question | Owner | Priority |
|---|---|---|---|
| OQ-1 | Should `_resolve_pack_and_source_type` have a dedicated unit test that verifies `supported_source_types[0]` is returned, including the empty-list edge case? Currently only covered end-to-end by the CI graph tests. | Backend | P1 |
| OQ-2 | Should `enforce_budgets` be tested with `objects=[]` explicitly? The function's loop is trivially safe, but the contract is undocumented for this case. | Backend | P1 |
| OQ-3 | The combined per-segment + per-source budget interaction (both caps binding simultaneously) has no dedicated test. Should one be added given Phase B depends on budget correctness for backfill? | Backend | P2 |
| OQ-4 | `validate_identifier` does not test an uppercase `domain_pack` value via the API layer. The regex `^[a-z0-9_\-]{1,64}$` rejects uppercase — should this be a parametrize case in `test_sources.py`? | Backend | P2 |
| OQ-5 | `test_extraction_graph.py` has no test for a document with status other than `"embedded"` (e.g. `"claims_extracted"`) — the graph node returns early with `STATUS_EXTRACTION_FAILED`. Should this be added to guard the status lifecycle guard? | Backend | P2 |
