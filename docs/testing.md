# Testing

> **Phase 3 Status: Implemented** — integration coverage for ingestion, extraction, and chat plus focused CLI/LLM unit tests.

Read [docs/specs/operations.md](specs/operations.md) for phase-level validation gates.

## Running Tests

```sh
# All tests (includes slow integration tests)
python -m pytest tests/ -v

# Fast unit tests only — skips @pytest.mark.slow tests
python -m pytest tests/ -v -m "not slow"
```

**Requirements:**

- Docker is preferred; when Docker is available, testcontainers starts `pgvector/pgvector:pg16` automatically.
- If Docker is unavailable, the suite falls back to local Postgres at `postgresql+asyncpg://nexus:nexus@localhost:5432/nexus`.
- A `.env` file must exist with `DATABASE_URL` and `APP_SECRET` set (the test harness overrides the DB URL at runtime when needed).
- Tests marked `@pytest.mark.slow` require a live database and a running FastAPI server. They are excluded from fast-unit CI runs via `-m "not slow"`. The `slow` marker is registered in `pyproject.toml` under `[tool.pytest.ini_options]`.

Run a single file:

```sh
python -m pytest tests/test_sources.py -v
python -m pytest tests/test_ingestion.py -v
python -m pytest tests/test_chat_api.py tests/test_chat_graph.py -v
```

## Test Architecture

The suite mixes **integration tests** against a real PostgreSQL + pgvector database with **focused unit tests** for renderers and LLM client behavior. Database-backed tests do not mock the persistence layer.

Key fixtures (in `tests/conftest.py`):

| Fixture | Scope | Purpose |
|---|---|---|
| `db_url` | session | Uses a testcontainers Postgres URL when Docker is available, otherwise the local fallback URL |
| `run_migrations` | session, autouse | Runs `alembic upgrade head` via subprocess before any test |
| `async_engine` | function | Fresh asyncpg engine per test (avoids event-loop conflicts) |
| `session_factory` | function | `async_sessionmaker` bound to the per-test engine |
| `clean_db` | function, autouse | Truncates all tables (reverse dependency order) before each test |
| `client` | function | `httpx.AsyncClient` wired to a minimal FastAPI app without an embedder |
| `client_with_embedder` | function | Same test app, but with a deterministic mock embedder for search/chat routes |

Network calls (RSS fetches, URL fetches) are patched with `unittest.mock.AsyncMock` to keep tests fast and hermetic.

## Test Files

### API and graph integration

- `tests/test_sources.py` covers source management CRUD and validation.
- `tests/test_ingestion.py` covers text, URL, and RSS ingestion plus deduplication and provenance.
- `tests/test_chat_api.py` covers `/chat/answer` validation, insufficient-evidence behavior, and `503` error translation.
- `tests/test_chat_graph.py` covers hybrid span-plus-claim retrieval, active-claim filtering, deterministic citation ordering, citation-label normalization, and insufficient-evidence fallback.

### Focused unit tests

- `tests/test_cli_render.py` covers human and JSON rendering for status, documents, claims, search, extraction summaries, and chat answers.
- `tests/test_cli_e2e.py` covers CLI command wiring with monkeypatched HTTP/database boundaries.
- `tests/test_llm_client.py` covers OpenRouter response validation, token accounting, and `run_type` recording for both extraction and chat answers.

### Phase A — semantic-object and projection unit tests

All Phase A tests are no-DB and no-LLM; they exercise the new extraction layer in isolation.

- `tests/domain_packs/test_loader.py` — v3 domain-pack loader: Pydantic validation, required fields, back-compat key presence.
- `tests/intelligence/test_semantic_object_schema.py` — `CoreType`, `SemanticObject`, `SemanticExtractionOutput` schema validation.
- `tests/intelligence/test_extract_semantic_objects_prompt.py` — `build_user_prompt` and `build_correction_prompt` output structure and pack injection.
- `tests/intelligence/test_projection.py` — `validate_object`, `project`, `enforce_budgets` unit coverage.
- `tests/intelligence/test_a6_projection_regression.py` — regression smoke: 5 representative `SemanticObject` payloads (`model_release`, `benchmark_result`, `funding_event`, `security_issue`, `forecast`) through the full validate→budgets→project chain using the real `personal_ai_tech` pack; asserts correct `claim_type` projection, presence of `_v0_7` / `_function` / `_domain_family`, and budget enforcement.
- `tests/intelligence/test_judge_semantic_object_prompt.py` — `build_judge_prompt` and `JudgeVerdict` schema for the T2 judge scaffold.

### Phase B — capsule layer and classifier tests

Phase B adds three DB-bound tests (require Docker / Postgres via testcontainers) and one no-DB classifier test.

- `tests/db/test_capsule_schema.py` — migration 0005 schema correctness: CHECK constraints on `core_type`, `lifecycle_state`, `escalation_state`; UNIQUE on `idempotency_key`; FK cascade for `capsule_segments`; ORM backrefs (`Document.capsules`, `SemanticCapsule.segments`).
- `tests/intelligence/test_capsules_dual_write.py` — `store_claims` writes `SemanticCapsule` + `CapsuleSegment` rows in the same transaction as `Claim` + `ClaimEvidence`; asserts row counts, idempotency key, and embedding dimension (384).
- `tests/intelligence/test_capsule_backfill.py` — `capsule_from_claim` reads `Claim.entities_json["_v0_7"]`, writes capsule rows; reruns are idempotent via `idempotency_key` UNIQUE conflict handling.
- `tests/intelligence/test_resolve_pack_and_source_type.py` — no-DB; 4-pass classifier: URL domain match, title regex match, pack fallback, and safety-net `"ai_news_article"`; spoof-resistance (suffix attacks); `(?-i)` case-sensitive override.

The gold set for the Phase B eval runner is `evals/gold/semantic_objects/ai_tech_v3.yaml` (10 examples, 6 `mvp_claim_types`). The legacy gold set `evals/gold/claim_extraction/ai_tech_v2.yaml` is obsolete — the `SemanticObjectJudge` replaces `ClaimExtractionJudge`.

### Phase C — reasoning node and validation harness tests

Phase C adds four new test files.

Pure unit tests (no DB, no LLM):

- `tests/intelligence/test_capsules.py` — 7 unit tests for `build_capsule_row`: field mapping, idempotency key generation, segment count, embedding dimension, and `created_by_tier` values.
- `tests/intelligence/test_judge_wiring.py` — 6 unit tests for `_resolve_t2_model` (pack override, fallback to `settings.t2_model`, missing key) and `_capsule_to_obj_for_judge` (field reconstruction from capsule row).
- `tests/intelligence/test_relation_classification.py` — 9 tests for `build_relation_prompt` output structure, `RelationClassification` Pydantic schema validation, and `classify_relations` node short-circuit behavior when over budget and "none"-result skipping.

Slow integration tests:

- `tests/test_validation_harness.py` — 5 tests marked `@pytest.mark.slow`: text ingest, RSS ingest, status, document inspection, and semantic search. Run against a real database and live server. Excluded from fast-unit CI via `-m "not slow"`.

## Critical Invariants Tested

- Duplicate documents (by URL or content hash) are skipped, not double-inserted.
- Every ingested document has a `source_id` that resolves to a real `sources` row.
- `source_type` validation is enforced at the API layer (422 for unknown types).
- RSS ingestion rejects non-RSS sources (422) and missing sources (404).
- Empty text is rejected before persistence (422).
- Blocked URL schemes (`file://`, etc.) are rejected (422).
- Chat answers do not call the model when no embedded evidence is available.
- Only active claims linked through `claim_evidence` are injected into chat context.
- Unknown, malformed, or citation-free model responses degrade to the insufficient-evidence answer instead of exposing fabricated citations.

## Required Test Types (Future Phases)

- Unit tests for chunking, span ordering, and embedding helpers.
- Schema validation tests for richer LLM extraction and synthesis outputs.
- Worker tests for job orchestration and retry behavior.
- End-to-end fixture tests: ingest a source → produce spans, claims, and a grounded answer.
- Agent/model run logging with status and cost estimate.
