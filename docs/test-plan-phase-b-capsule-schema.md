# Test Plan — Phase B: Capsule-Schema Foundation

| Field | Value |
|---|---|
| **VERDICT** | WARN |
| **MERGE_BLOCKING** | no |
| **Date** | 2026-06-03 |
| **Branch** | `phase-b-implementation` |
| **Diff base** | `244fb3e..HEAD` (15 commits, 35 files, +4081/-496) |
| **Author** | test-plan-writer subagent |

**Verdict rationale:** All P0 cases and most P1 cases are covered by the Phase B
test suite. Three gaps prevent a clean PASS: (1) the `nexus capsules backfill` CLI
command has no Typer `CliRunner` smoke test — the plan (B3) called for one and
`test_cli_e2e.py` does not include it; (2) the `_aggregate_scores` denominator fix
(commit `0332700`) has no unit test for the specific fixed behaviour (error example
counts as 0, denominator is unchanged); and (3) the `build_capsule_row` refactor
(commit `4a052b4`) is exercised transitively through `test_happy_path_single_object`
and `test_capsule_from_claim_pure_function`, but there is no dedicated unit test for
`build_capsule_row` directly (e.g. confirming both extraction and backfill callers
delegate to the same function). All three gaps are low-risk but documented as
required follow-ups. All DB-integration tests are CI-only (Docker/testcontainers).

---

## 1. Summary

Phase B promotes the in-memory `SemanticObject` produced by Phase A into durable
database rows. It introduces six new tables (migration 0005), a dual-write path that
writes capsules in the same transaction as claims, a backfill command for existing
Phase A data, a URL+title classifier for source-type detection, and a port of the
eval runner to the `SemanticExtractionOutput`/`SemanticObjectJudge` path.

The `/simplify` refactor (commit `4a052b4`) extracts `build_capsule_row` into
`app/intelligence/capsules.py` as the single source of truth for SemanticObject →
capsule-column mapping, which both `store_claims` and `capsule_from_claim` delegate
to.

Key test additions in Phase B:
- `tests/db/conftest.py` + `tests/db/test_capsules_migration.py` — 17+ DB-bound tests
- `tests/intelligence/test_capsules_dual_write.py` — 4 DB-bound tests + embedded
  assertions
- `tests/intelligence/test_capsule_backfill.py` — 4 DB-bound + 1 pure-unit test
- `tests/intelligence/test_resolve_pack_and_source_type.py` — 23+ pure-unit tests
- `tests/intelligence/test_projection.py` — extended with idempotency-key tests
- `tests/evaluation/test_judges.py`, `test_metrics.py`, `test_runner.py`,
  `test_datasets.py` — updated for new types

---

## 2. Scope

### In scope

- **B1** — Migration 0005: six tables, indexes, CHECK constraints, FK behaviours,
  downgrade round-trip.
- **B2** — Dual-write: transactional atomicity, capsule+segment co-write,
  embedding presence/dimensions, idempotency-key determinism, field mapping.
- **B3** — Backfill: `_v0_7` → capsule, idempotency, `--dry-run`, orphan/no-blob
  skip, multi-source-ref, `capsule_from_claim` field mapping.
- **B4** — Source-type classifier: URL-domain pass, title-regex pass, URL-beats-title
  precedence, suffix-spoof rejection, fallback chain, empty supported_source_types.
- **B5** — Eval port: `SemanticExtractionOutput` SUT, `SemanticObjectJudge` scoring,
  `mvp_claim_type_projection_accuracy` and capsule-only metrics, legacy deletion.
- **Refactor (4a052b4)** — `build_capsule_row` as single source of truth.
- **No-regression** — Phase A chat path, projection layer, A6 regression smoke.

### Out of scope

- T2 judge wiring (Phase C).
- Capsule retrieval / `/chat/answer` port (Phase D).
- Lifecycle / consolidation workers (Phase E).
- Pack inheritance resolution (Phase F).
- `semantic_relations`, `theses`, `decision_artefacts` writers (tables exist but
  have no write path in Phase B).

---

## 3. Environment Constraints

| Category | Status |
|---|---|
| Pure unit tests (no DB) | Runnable locally with `--noconftest` |
| DB integration tests (`test_capsules_migration.py`, `test_capsules_dual_write.py`, `test_capsule_backfill.py`, `test_extraction_graph.py`, `test_cli_e2e.py`) | **CI-only** — require Docker (testcontainers pgvector/pgvector:pg16) or a local Nexus dev DB with pgvector |
| OpenRouter / LLM calls | None — all graph tests use `FakeLLMClient` |

Local run command for non-DB tests:
```
python -m pytest tests/intelligence/ tests/domain_packs/ tests/evaluation/ -v --noconftest
```

---

## 4. Coverage Mapping

| Acceptance Criterion | Test IDs | Status |
|---|---|---|
| **B1** — 6 new tables with correct columns / CHECK constraints / FK behaviours | MIG-1 through MIG-9 | Covered (CI-only) |
| **B1** — Migration reversible (downgrade 0004 → re-upgrade head) | MIG-10 | Covered (CI-only) |
| **B2** — Every accepted SemanticObject produces Capsule + N CapsuleSegment in same transaction as Claim + ClaimEvidence | DW-1, DW-2 | Covered (CI-only) |
| **B2** — Capsule.embedding is 384-dim non-null | DW-1, DW-4 | Covered (CI-only) |
| **B2** — idempotency_key is deterministic (formula, ordering, cross-path parity) | DW-1 (assert), PR-9 | Covered |
| **B2** — Capsule rollback if commit fails (transactional atomicity) | DW-3 | Covered (CI-only) |
| **B3** — `nexus capsules backfill` reads `_v0_7` blobs and writes capsules | BF-1, BF-2, BF-3 | Covered (CI-only) |
| **B3** — Backfill is idempotent (rerun skips already-written capsules) | BF-2 | Covered (CI-only) |
| **B3** — `--dry-run` does not commit | BF-3 | Covered (CI-only) |
| **B3** — `capsule_from_claim` field mapping correctness (plan §6) | BF-5 (`test_capsule_from_claim_pure_function`) | Covered |
| **B3** — Multi-source-ref claim → N capsule_segments | BF-4 | Covered (CI-only) |
| **B3** — CLI `nexus capsules backfill --dry-run` exit-code / output smoke | *(no dedicated CLI-level test)* | **Gap (P1)** |
| **B4** — URL hostname match routes to correct v3 source-type profile | ST-1 through ST-9 | Covered |
| **B4** — Title regex IGNORECASE + precedence passes | ST-10 through ST-15, ST-17 | Covered |
| **B4** — URL-beats-title precedence | ST-16 | Covered |
| **B4** — Suffix-spoof URLs rejected | ST-8 (`test_url_suffix_spoof_does_not_match`) | Covered |
| **B4** — Pack-level fallback (Pass 3 — `supported_source_types[0]`) | ST-18 | Covered |
| **B4** — Empty `supported_source_types` → `"ai_news_article"` safety net | ST-19 | Covered |
| **B5** — `runner.py` uses `SemanticExtractionOutput`; no `ExtractedClaim` import | EV-1, EV-2, EV-3 | Covered |
| **B5** — `SemanticObjectJudge` produces `mvp_claim_type_projection_accuracy` | EV-3, JU-1 | Covered |
| **B5** — `nexus eval run` produces non-NULL capsule-only metric (`core_type_accuracy`) | EV-3 | Covered |
| **B5** — `_aggregate_scores` denominator denominator fixed (error counts as 0.0, not excluded) | EV-4 | Covered (partially — see Gap section) |
| **B5** — Gold set `ai_tech_v3.yaml` loaded without error | DS-1 | Covered |
| **Refactor** — `build_capsule_row` single source of truth; both callers delegate | BF-5, DW-1 (transitively) | Covered (transitively) |
| **Refactor** — Direct unit test for `build_capsule_row` signature / output | *(no dedicated test)* | **Gap (P2)** |
| **No regression** — Phase A chat reads claims (chat tests pass) | *(existing `test_chat_graph.py`, `test_chat_api.py`)* | Covered (CI-only) |
| **No regression** — A6 projection smoke (`test_a6_projection_regression.py`) | *(existing suite)* | Covered |
| **No regression** — `ExtractedClaim`/`ExtractionOutput` deleted from tree | Plan §11 grep gate | Covered (manual gate) |

---

## 5. Test Cases

### 5.1 Migration (B1) — `tests/db/test_capsules_migration.py` (CI-only)

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| MIG-1 | P0 | `TestTablesExist::test_table_present[semantic_capsules]` | `semantic_capsules` table exists after upgrade head | **Implemented (CI-only)** |
| MIG-2 | P0 | `TestTablesExist::test_table_present[capsule_segments]` | `capsule_segments` table exists | **Implemented (CI-only)** |
| MIG-3 | P0 | `TestTablesExist::test_table_present[semantic_relations]` | `semantic_relations` table exists | **Implemented (CI-only)** |
| MIG-4 | P0 | `TestTablesExist::test_table_present[theses]` | `theses` table exists | **Implemented (CI-only)** |
| MIG-5 | P0 | `TestTablesExist::test_table_present[decision_artefacts]` | `decision_artefacts` table exists | **Implemented (CI-only)** |
| MIG-6 | P0 | `TestTablesExist::test_table_present[domain_packs]` | `domain_packs` table exists | **Implemented (CI-only)** |
| MIG-6b | P1 | `TestTablesExist::test_embedding_is_vector_type` | `embedding` column is pgvector `vector` UDT (not `float[]`) | **Implemented (CI-only)** |
| MIG-7 | P1 | `TestIndexes::test_expected_indexes_present` | All 8 expected indexes are present (source_id, document_id, claim_id partial, segment_id, domain, relations-source, relations-target-capsule, relations-target-thesis) | **Implemented (CI-only)** |
| MIG-8 | P0 | `TestCheckConstraints::test_check_constraint_rejects_invalid_value[core_type-banana]` | `core_type` CHECK rejects unknown value | **Implemented (CI-only)** |
| MIG-8b | P0 | `TestCheckConstraints::test_check_constraint_rejects_invalid_value[lifecycle_state-frozen]` | `lifecycle_state` CHECK rejects unknown value | **Implemented (CI-only)** |
| MIG-8c | P0 | `TestCheckConstraints::test_check_constraint_rejects_invalid_value[escalation_state-ignored]` | `escalation_state` CHECK rejects unknown value | **Implemented (CI-only)** |
| MIG-8d | P0 | `TestCheckConstraints::test_check_constraint_rejects_invalid_value[created_by_tier-t9]` | `created_by_tier` CHECK rejects unknown tier | **Implemented (CI-only)** |
| MIG-8e | P1 | `TestCheckConstraints::test_relations_xor_constraint` | `semantic_relations` row with neither `target_capsule_id` nor `target_thesis_id` violates XOR CHECK | **Implemented (CI-only)** |
| MIG-9a | P1 | `TestUniqueAndForeignKeys::test_idempotency_key_unique` | Duplicate `idempotency_key` raises `IntegrityError` | **Implemented (CI-only)** |
| MIG-9b | P1 | `TestUniqueAndForeignKeys::test_source_delete_cascades_capsule` | Deleting a source cascades to delete its capsules | **Implemented (CI-only)** |
| MIG-9c | P1 | `TestUniqueAndForeignKeys::test_capsule_delete_cascades_segments` | Deleting a capsule cascades to delete its `capsule_segments` rows | **Implemented (CI-only)** |
| MIG-9d | P1 | `TestUniqueAndForeignKeys::test_claim_delete_sets_capsule_claim_id_null` | Deleting a claim sets `semantic_capsules.claim_id` to NULL (`ON DELETE SET NULL`) | **Implemented (CI-only)** |
| MIG-10 | P0 | `TestDowngrade::test_round_trip` | `alembic downgrade 0004` removes all 6 tables; `alembic upgrade head` re-creates them | **Implemented (CI-only)** |

### 5.2 Dual-Write (B2) — `tests/intelligence/test_capsules_dual_write.py` (CI-only)

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| DW-1 | P0 | `test_happy_path_single_object` | 1 SemanticObject → 1 Claim + 1 ClaimEvidence + 1 SemanticCapsule + 1 CapsuleSegment; every capsule field maps to plan §6 values; `idempotency_key` matches `build_capsule_idempotency_key` output exactly; embedding is 384-dim | **Implemented (CI-only)** |
| DW-2 | P1 | `test_multi_source_refs` | 1 object with 2 `source_refs` → 1 capsule + 2 `capsule_segments`; segment IDs match span IDs; 2 `claim_evidence` rows | **Implemented (CI-only)** |
| DW-3 | P0 | `test_transaction_atomicity` | Session commit patched to raise `IntegrityError` → both `Claim` and `SemanticCapsule` row counts are zero (single-transaction rollback) | **Implemented (CI-only)** |
| DW-4 | P1 | `test_embedding_present` | Capsule embedding is non-NULL and all values are finite floats (not nan/inf from a broken model load) | **Implemented (CI-only)** |

### 5.3 Backfill (B3) — `tests/intelligence/test_capsule_backfill.py`

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| BF-1 | P1 | `test_backfill_skips_phase_a_claim_without_v07_key` | Claims without `_v0_7` key are skipped; `result.claims_skipped_no_v07 >= 1`; no capsule rows written; no errors | **Implemented (CI-only)** |
| BF-2 | P0 | `test_backfill_idempotent` | First run writes ≥1 capsule; second run produces 0 new capsules and increments `claims_skipped_already_backfilled`; only 1 capsule row exists | **Implemented (CI-only)** |
| BF-3 | P0 | `test_backfill_dry_run` | `dry_run=True` reports ≥1 would-write count but leaves 0 rows in DB | **Implemented (CI-only)** |
| BF-4 | P1 | `test_backfill_multi_source_ref` | Claim with 3 `source_refs` → 1 capsule + 3 `capsule_segments`; all segment span IDs match | **Implemented (CI-only)** |
| BF-5 | P0 | `test_capsule_from_claim_pure_function` | Pure unit: every capsule column maps correctly to `_v0_7` blob per plan §6; `idempotency_key == build_capsule_idempotency_key(...)` exactly; deterministic UUID from key; N segments = N source_refs; `role` propagates from `evidence_roles` lookup; fallback to `"support"` when span not in map; `lifecycle_state="active"`, `escalation_state="none"`, `created_by_tier="backfill"` | **Implemented** |
| BF-6 | P1 | CLI smoke: `nexus capsules backfill --dry-run` exits 0 and prints count | *(gap — no `CliRunner` test in `test_cli_e2e.py`)* | **Gap (P1)** |

### 5.4 Source-Type Classifier (B4) — `tests/intelligence/test_resolve_pack_and_source_type.py`

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| ST-1 | P1 | `TestUrlDomainMatch::test_techcrunch_matches_ai_news_article` | `techcrunch.com` URL → `ai_news_article` | **Implemented** |
| ST-2 | P1 | `TestUrlDomainMatch::test_arxiv_matches_research_paper` | `arxiv.org` URL → `research_paper_or_report` | **Implemented** |
| ST-3 | P1 | `TestUrlDomainMatch::test_openai_blog_matches_model_release_note` | `openai.com/blog/...` path prefix → `model_release_note` | **Implemented** |
| ST-4 | P1 | `TestUrlDomainMatch::test_epoch_ai_matches_forecast` | `epoch.ai` URL → `forecast_or_opinion` | **Implemented** |
| ST-5 | P1 | `TestUrlDomainMatch::test_nvd_nist_matches_security_disclosure` | `nvd.nist.gov` URL → `security_or_safety_disclosure` | **Implemented** |
| ST-6 | P1 | `TestUrlDomainMatch::test_url_match_returns_correct_pack` | URL match returns `personal_ai_tech` pack instance (pack identity check) | **Implemented** |
| ST-7 | P1 | `TestUrlDomainMatch::test_source_url_used_when_document_url_is_none` | `Source.url` is fallback when `Document.url` is None | **Implemented** |
| ST-8 | P0 | `TestUrlDomainMatch::test_url_suffix_spoof_does_not_match` | `notarxiv.org` must NOT match `arxiv.org` hint (suffix-spoof rejection) | **Implemented** |
| ST-9 | P1 | `TestUrlDomainMatch::test_url_path_hint_requires_path_prefix` | `openai.com/research/...` does NOT match the `openai.com/blog` path hint | **Implemented** |
| ST-10 | P1 | `TestTitleRegexMatch::test_introducing_capital_matches_product_announcement` | `"Introducing Claude 3.7"` → `product_or_tool_announcement` | **Implemented** |
| ST-11 | P1 | `TestTitleRegexMatch::test_security_cve_title_matches_security_disclosure` | CVE-prefixed title → `security_or_safety_disclosure` | **Implemented** |
| ST-12 | P1 | `TestTitleRegexMatch::test_funding_series_b_matches_funding_update` | Series B title → `funding_or_company_update` | **Implemented** |
| ST-13 | P1 | `TestTitleRegexMatch::test_mmlu_benchmark_title_matches_benchmark_report` | MMLU title → `benchmark_report` | **Implemented** |
| ST-14 | P1 | `TestTitleRegexMatch::test_source_name_used_when_title_is_none` | `Source.name` fallback when `Document.title` is None | **Implemented** |
| ST-15 | P1 | `TestTitleRegexMatch::test_announcing_pricing_routes_to_pricing_not_product` | Common-noun prefix `"Announcing our..."` does NOT match product_or_tool_announcement (regex lookahead); falls to `pricing_or_terms_update` | **Implemented** |
| ST-16 | P0 | `TestUrlBeatsTitlePrecedence::test_url_match_wins_over_title_regex` | arxiv.org URL wins over `"Introducing..."` title — URL-domain pass always precedes title-regex pass | **Implemented** |
| ST-17 | P1 | `TestTitleRegexCaseInsensitive::test_lowercase_mmlu` | Lowercase `"mmlu"` still routes to `benchmark_report` (IGNORECASE) | **Implemented** |
| ST-17b | P1 | `TestTitleRegexCaseInsensitive::test_mixed_case_vulnerability` | Mixed-case `"VULNERABILITY"` routes to `security_or_safety_disclosure` | **Implemented** |
| ST-18 | P1 | `TestFallbackToSupportedSourceTypes::test_no_match_falls_back_to_first_supported_type` | Unrecognised URL + title fall back to `pack.metadata.supported_source_types[0]` = `"ai_news_article"` | **Implemented** |
| ST-19 | P1 | `TestEmptySupportedSourceTypesSafetyNet::test_empty_supported_source_types_returns_ai_news_article` | Pack with empty `supported_source_types` → `"ai_news_article"` safety net | **Implemented** |
| ST-20 | P2 | `TestMultipleUrlMatchesDeclOrderWins::test_first_profile_wins_when_url_matches_multiple` | First pack-declaration-order profile wins | **Implemented** |
| ST-21 | P2 | `TestIdempotency::test_same_inputs_same_output` | Calling twice with identical inputs returns identical profile | **Implemented** |

### 5.5 Eval Port (B5) — `tests/evaluation/`

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| EV-1 | P1 | `TestSUTConfig::test_defaults` | `SUTConfig` defaults: `pack_id="personal_ai_tech"`, `source_type="ai_news_article"`, `temperature=0.0` | **Implemented** |
| EV-2 | P1 | `TestAggregateScores::test_averages_metrics` | `_aggregate_scores` averages all 10 metric keys including `mvp_claim_type_projection_accuracy` and `salience_precision` | **Implemented** |
| EV-3 | P0 | `TestExecuteRun::test_returns_eval_run_result` | `execute_run` uses `SemanticExtractionOutput` SUT call; patches `SemanticObjectJudge`; result includes `mvp_claim_type_projection_accuracy` and `core_type_accuracy` keys | **Implemented** |
| EV-4 | P1 | `TestAggregateScores::test_error_example_divides_by_full_count` | Error example (missing keys) counts as 0.0; denominator is `len(score_list)` not `len(non_empty)`; regression for commit `0332700` fix | **Implemented** |
| EV-5 | P2 | `TestExecuteRun::test_budget_gate_stops_execution` | `max_cost_usd=0.0` allows graph to run but no token spend occurs | **Implemented** |
| EV-6 | P1 | `TestExecuteRun::test_raises_if_dataset_not_registered` | Non-registered dataset raises `ValueError("not registered")` | **Implemented** |
| JU-1 | P0 | `TestSemanticObjectJudge::test_perfect_match_score` | Perfect-match verdict produces `precision=1.0`, `recall=1.0`, `f1=1.0`, `mvp_claim_type_projection_accuracy=1.0`, `core_type_accuracy=1.0`, `domain_family_accuracy=1.0`, `mean_capsule_completeness=0.9` | **Implemented** |
| JU-2 | P1 | `TestSemanticObjectJudge::test_missing_object_lowers_recall` | Missing gold object drives `recall=0.0` | **Implemented** |
| JU-3 | P1 | `TestSemanticObjectJudge::test_spurious_object_lowers_precision` | Spurious pred object drives `precision=0.0` | **Implemented** |
| JU-4 | P1 | `TestSemanticObjectJudge::test_returns_per_pair_verdicts` | `per_pair_verdicts` key present with ≥1 entry | **Implemented** |
| JU-5 | P2 | `TestSemanticObjectJudge::test_both_empty_returns_perfect` | Both lists empty → `precision=1.0` | **Implemented** |
| DS-1 | P1 | (transitively: `test_runner.py` loads `Dataset` with `SemanticObjectExtractionExample`) | Gold set `ai_tech_v3.yaml` parses correctly via `load_dataset` | **Implemented** |

### 5.6 Idempotency Key (cross-cutting) — `tests/intelligence/test_projection.py`

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| PR-9 | P0 | `test_build_capsule_idempotency_key_is_deterministic` | Same inputs → same key; different text → different key; `source_refs` ordering does not affect key (sorted internally); different `domain_object_type` → different key; key shape matches `{doc_id}:{refs}:{type}:{sha256[:16]}` exactly | **Implemented** |

### 5.7 Phase A No-Regression Smoke

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| REG-1 | P0 | `test_a6_projection_regression.py::test_all_five_objects_accepted_by_validator` | All 5 fixture objects still accepted (projection layer unchanged) | **Implemented** |
| REG-2 | P0 | `test_a6_projection_regression.py::test_all_five_objects_project_to_correct_claim_types` | Projection still produces `[model_release, benchmark_result, funding_event, security_issue, forecast]` | **Implemented** |
| REG-3 | P0 | `test_a6_projection_regression.py::test_forward_compat_stash_keys_present` | `_v0_7`, `_function`, `_domain_family` all present in every projected claim's `entities_json` | **Implemented** |
| REG-4 | P1 | `test_extraction_graph.py::test_happy_path_stores_claims` | Full extraction graph still writes Claim + ClaimEvidence (chat read path unaffected) | **Implemented (CI-only)** |

---

## 6. Edge Cases and Negative Tests

| ID | Priority | Description | Status |
|---|---|---|---|
| NEG-1 | P0 | `test_url_suffix_spoof_does_not_match`: `notarxiv.org` must NOT match `arxiv.org` (suffix-spoof via `_url_matches_domain`) | **Implemented** (ST-8) |
| NEG-2 | P0 | `test_relations_xor_constraint`: `semantic_relations` row with neither target raises `IntegrityError` | **Implemented** (MIG-8e) |
| NEG-3 | P0 | `test_transaction_atomicity`: capsule-write failure aborts matching Claim row (same-transaction invariant) | **Implemented** (DW-3) |
| NEG-4 | P0 | `test_backfill_idempotent`: re-running backfill skips already-backfilled claims via `idempotency_key` UNIQUE conflict (no duplicate rows) | **Implemented** (BF-2) |
| NEG-5 | P1 | `test_backfill_dry_run`: `dry_run=True` does not commit any rows | **Implemented** (BF-3) |
| NEG-6 | P1 | `test_backfill_skips_phase_a_claim_without_v07_key`: claim without `_v0_7` blob is silently skipped | **Implemented** (BF-1) |
| NEG-7 | P1 | `test_url_path_hint_requires_path_prefix`: `openai.com/research/...` does NOT match `openai.com/blog` hint | **Implemented** (ST-9) |
| NEG-8 | P1 | `test_announcing_pricing_routes_to_pricing_not_product`: regex lookahead prevents common-noun "announcing" from matching product_or_tool_announcement | **Implemented** (ST-15) |
| NEG-9 | P1 | `test_empty_supported_source_types_returns_ai_news_article`: empty list never causes `IndexError` | **Implemented** (ST-19) |
| NEG-10 | P1 | `TestCheckConstraints`: `core_type`, `lifecycle_state`, `escalation_state`, `created_by_tier` all reject invalid values at the DB layer | **Implemented** (MIG-8) |
| NEG-11 | P1 | `test_claim_delete_sets_capsule_claim_id_null`: claim deletion does not cascade-delete capsule | **Implemented** (MIG-9d) |
| NEG-12 | P1 | `test_capsule_from_claim_pure_function`: role fallback to `"support"` when span_id absent from `evidence_roles` dict | **Implemented** (BF-5) |
| NEG-13 | P2 | Orphaned-span skip (span cascade-deleted before backfill runs) | **Not explicitly tested** — `test_capsule_backfill.py` does not seed a document, delete its spans, and then run backfill. The B3 plan cited this case; the implementation presumably skips the claim, but there is no test asserting the exact skip-and-log behaviour. **Minor gap.** |
| NEG-14 | P2 | `build_capsule_row` called directly with `created_at` / `updated_at` non-None (backfill provenance path) | Covered transitively by `test_capsule_from_claim_pure_function` which asserts `capsule.created_at == _NOW` | **Covered transitively** |
| NEG-15 | P2 | `test_error_example_divides_by_full_count`: aggregate denominator fix (error = 0.0 contribution, not excluded) | **Implemented** (EV-4) |

---

## 7. Gaps and Required Actions

The following cases are absent from the current test suite. All are non-blocking for
merge (the immediate risk is low), but they should be added as follow-up commits.

| Gap ID | Priority | Description | Recommended Location |
|---|---|---|---|
| **GAP-1** | P1 | `nexus capsules backfill --dry-run` CLI smoke: invoke via `typer.testing.CliRunner`, assert exit code 0 and that the output contains a count line; assert `nexus capsules backfill` (no flag) writes rows. Neither `test_cli_e2e.py` nor `test_cli_runs.py` covers the `capsules` subcommand. | `tests/test_cli_e2e.py` (new `test_capsules_backfill_dry_run_cli` and `test_capsules_backfill_writes_rows_cli`) |
| **GAP-2** | P2 | Dedicated `build_capsule_row` unit test: call the function directly (not through the extraction graph), assert capsule fields and segment list match inputs. Currently only covered transitively through `test_happy_path_single_object` (which goes through the full graph) and `test_capsule_from_claim_pure_function` (which calls the slightly higher-level `capsule_from_claim`). The `/simplify` refactor made `build_capsule_row` the canonical function; it merits its own test in `test_projection.py` or a new `tests/intelligence/test_capsules.py`. | `tests/intelligence/test_capsules.py` (new) |
| **GAP-3** | P2 | Orphaned-span backfill skip: seed a claim with `_v0_7` referencing a span, delete the span (simulating cascade-delete after document removal), run backfill, assert the claim is skipped and logged rather than raising an error. | `tests/intelligence/test_capsule_backfill.py` (new `test_backfill_skips_orphaned_span_claim`) |

**REQUIRED_ACTIONS** (for post-merge follow-up, not blocking):
1. Add `test_capsules_backfill_dry_run_cli` and `test_capsules_backfill_writes_rows_cli` in `tests/test_cli_e2e.py` — covers GAP-1 (P1).
2. Add `tests/intelligence/test_capsules.py::test_build_capsule_row_direct` — covers GAP-2 (P2).
3. Add `test_backfill_skips_orphaned_span_claim` in `tests/intelligence/test_capsule_backfill.py` — covers GAP-3 (P2).

---

## 8. Fixtures and Setup Requirements

### Local (no DB, `--noconftest`)

- No additional setup.
- `test_resolve_pack_and_source_type.py`: pure unit, uses `monkeypatch` + `tmp_path`.
- `test_projection.py`: imports `load_pack("personal_ai_tech")` at module level from
  real YAML on disk.
- `test_capsule_backfill.py::test_capsule_from_claim_pure_function`: pure unit, no DB.

### CI (DB-required)

- `tests/db/conftest.py`: self-contained conftest that spins up `pgvector/pgvector:pg16`
  via `testcontainers` (falls back to `postgresql+asyncpg://nexus:nexus@localhost:5432/nexus`
  when Docker is unavailable). Runs `alembic upgrade head` once per session via subprocess.
  Provides `db_url`, `async_engine`, `session_factory` fixtures scoped to session.
- `tests/conftest.py` (top-level): provides `session_factory` for `test_capsules_dual_write.py`,
  `test_capsule_backfill.py`, `test_extraction_graph.py`, `test_cli_e2e.py`. Same
  testcontainer / local fallback strategy.
- All DB tests require `pgvector` extension. The `pgvector/pgvector:pg16` image
  pre-installs it.
- `SKIP=pytest-fast` per the standing precedent applies.

### Pre-commit environment

- `tests/db/conftest.py` is intentionally isolated from the parent `tests/conftest.py`
  import chain (`langgraph.checkpoint.postgres`) so migration tests can be collected
  independently of the full API stack.

---

## 9. Out of Scope

| Area | Reason |
|---|---|
| `semantic_relations` write path | No writer in Phase B; first writer is Phase C (T2 judge wiring). |
| `theses` / `decision_artefacts` write paths | No writers in Phase B; Phase E. |
| Phase D capsule retrieval (`/chat/answer` port) | Not in Phase B scope. |
| Pack inheritance resolution (`parent_pack_id`) | Column exists; resolution logic deferred to Phase F. |
| HNSW pgvector index | Added in Phase D when retrieval needs it. |
| T1 source-type classifier | Phase G concern; Phase B uses declarative YAML heuristics. |
| `span_extractions` table freshness after dual-write | Pre-existing coverage in `test_extraction_graph.py::test_extraction_populates_span_extractions_table`. |

---

## 10. Open Questions

| # | Question | Owner | Priority |
|---|---|---|---|
| OQ-1 | Should the `nexus capsules backfill` CLI smoke test live in `test_cli_e2e.py` (requires DB fixture) or in a new `tests/intelligence/test_capsule_backfill_cli.py` (pure unit with mocked `backfill_capsules`)? The existing `test_cli_e2e.py` pattern uses real DB fixtures; a pure unit mock would be faster but thinner. | Backend | P1 |
| OQ-2 | The orphaned-span skip path (NEG-13) is described in the B3 plan but has no test. At what point in Phase D / E (when span cleanup might actually run) should this case be promoted to P1? | Backend | P2 |
| OQ-3 | `build_capsule_row` now has a `source_id: uuid.UUID | None` parameter. The `None` branch (when `source_id` is not resolvable) has no explicit test coverage. Is this branch reachable in production, and if so, should a negative test be added? | Backend | P2 |
| OQ-4 | The `nexus eval run --pack-id X --source-type Y` prompt-prefix behaviour (P2 acceptance criterion B5) is covered only by `TestSUTConfig::test_defaults` (asserting defaults). A positive test that `--pack-id` / `--source-type` overrides actually change the prompt sent to the SUT would strengthen B5 coverage. | Backend | P2 |
