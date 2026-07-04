# Docs Index

This repository is bootstrapped with an agent harness and supporting docs. Use this index as the starting point for repo-specific context.

## Core Docs

- [AGENTS.md](../AGENTS.md)
- [README (demo guide)](../README.md)
- [Agent Harness](agent-harness.md)
- [Project Specs](specs/README.md)
- [Architecture](architecture.md)
- [Database](database.md)
- [Patterns](patterns.md)
- [Testing](testing.md)
- [Commands](commands.md)
- [Nexus CLI](cli.md)
- [Memory Benchmark Plan](benchmarks/memory-benchmark-plan.md)
- [LongMemEval Benchmark Report](benchmarks/longmemeval-2026-07-04.md) — external benchmark (H7), 0.355→0.709 accuracy
- [Changelog](changelog.md)
- [Insights](insights.md)
- [CI docs](ci/README.md)

## Intelligence Prompts

`app/intelligence/prompts/` — LLM prompt builders and output schemas.

| Module | Responsibility |
|---|---|
| `extract_semantic_objects.py` | T2 extraction prompt; `build_user_prompt`, `build_correction_prompt`, `SYSTEM_PROMPT` |
| `judge_semantic_object.py` | T2 judge prompt; `JudgeVerdict` schema, `build_judge_prompt` — wired as `judge_capsules` node (Phase C) |
| `classify_relations.py` | T2 relation classifier; `RelationClassification` schema, `build_relation_prompt`, `SYSTEM_PROMPT` — wired as `classify_relations` node (Phase C) |
| `chat_answer.py` | Chat answer prompt; question/capsule-context builder for grounded single-turn and session answers |
| `classify_intent.py` | Query-intent classifier; `IntentClassification` schema, `build_classify_prompt`, `SYSTEM_PROMPT` — wired as `classify_intent` node (Phase D) |

## Evaluation Framework

`app/evaluation/` — LLM-as-a-Judge offline evaluation pipeline.

| Module | Responsibility |
|---|---|
| `datasets.py` | Pydantic schemas; `load_dataset()` with SHA-256 checksum |
| `metrics.py` | `precision_recall_f1`, `precision_at_k`, `ndcg_at_k`, `align_claims` |
| `judges.py` | `SemanticObjectJudge` (active, Phase B); Phase 4 stubs for brief synthesis and grounded-answer judges |
| `runner.py` | `execute_run()` — SUT invocation (`SemanticExtractionOutput`), judge scoring, budget gate, Postgres persistence |
| `meta_eval.py` | `compute_kappa`, `compute_pearson`, `load_human_labels` — judge calibration |

Gold datasets: `evals/gold/` — `semantic_objects/ai_tech_v3.yaml` (10 examples), `span_retrieval/queries_v1.yaml` (20 examples).
Human calibration labels: `evals/human_labels/claim_extraction.yaml` (6-seed set).

CLI entry point: `app/cli/eval.py` — `nexus eval` sub-app. See [Commands](commands.md) for full usage.

## Phase C Test Files

| File | Type | Coverage |
|---|---|---|
| `tests/intelligence/test_capsules.py` | Unit (no DB) | `build_capsule_row` field mapping, idempotency key, embedding dim |
| `tests/intelligence/test_judge_wiring.py` | Unit (no DB) | `_resolve_t2_model`, `_capsule_to_obj_for_judge` helpers |
| `tests/intelligence/test_relation_classification.py` | Unit (no DB) | `build_relation_prompt`, `RelationClassification` schema, `classify_relations` short-circuit and "none"-skip |
| `tests/intelligence/test_theses.py` | Unit (no DB) | `build_thesis_row` field mapping, tier/confidence validation, `synthesize_theses_from_relations` union-find clustering (mocked session) |
| `tests/intelligence/test_decision_artefacts.py` | Unit (no DB) | `build_decision_artefact_row` field mapping, tier validation |
| `tests/intelligence/test_tiers.py` | Unit (no DB) | `validate_writer_tier` accepts/rejects `WRITER_TIERS` (`t2`/`t3`/`t4`) |
| `tests/intelligence/test_reasoning_layer_db.py` | Integration (`@pytest.mark.slow`) | DB-bound: `judge_capsules` unary relation row, `classify_relations` binary relation row, C1→C2→C3 thesis round-trip (real Postgres, mocked LLM) |
| `tests/test_validation_harness.py` | Integration (`@pytest.mark.slow`) | End-to-end: text/RSS ingest, status, document inspection, semantic search |

## Phase D Test Files

| File | Type | Coverage |
|---|---|---|
| `tests/intelligence/test_chat_intent.py` | Unit (no DB) | `_run_classify_intent` — LLM match, unknown fallback, empty-intents skip, network/schema-error fallback |
| `tests/intelligence/test_chat_scoring.py` | Unit (no DB) | `compute_hybrid_score` — semantic weighting, object-family priority boost, stubbed weights, recency normalization |
| `tests/intelligence/test_chat_assembly.py` | Unit (no DB) | `estimate_tokens`, `_assemble_within_budget` (budget/`top_k`/first-block rules), `_build_evidence_map` (grouping, span cap, truncation) |
| `tests/intelligence/test_chat_graph.py` | Unit (mocked DB/LLM) | `classify_intent`/`retrieve_capsules` nodes, capsule citation formatting, capsule→span evidence attachment, insufficient-evidence path, label normalization |

## Phase D/E/F Test Files (hackathon: retrieval, lifecycle, consolidation, benchmark)

| File | Type | Coverage |
|---|---|---|
| `tests/test_chat_context_assembly.py` | Unit (no DB) | `compute_hybrid_score` authority/evidence/relation inputs, `evidence_strength` ordering, `include`-category block assembly |
| `tests/test_llm_client_config.py` | Unit (no DB) | `settings.llm_api_key` fallback, `LLMClient` custom `base_url` |
| `tests/intelligence/test_lifecycle.py` | Integration (`@pytest.mark.slow`) | `apply_lifecycle_transitions` — all 6 rule precedences, dry-run rollback, terminal-state protection, historical-event exclusion from the supersession heuristic |
| `tests/intelligence/test_consolidation.py` | Integration (`@pytest.mark.slow`) | `consolidate_domain` — thesis creation, dry-run, dedup on re-run |
| `tests/test_eval_memory_cli.py` | Unit (no DB) | `nexus eval memory run`/`report` — lazy runner import, missing-fixtures/report errors |
| `tests/benchmarks/test_scoring.py` | Unit (no I/O) | `score_answer`/`aggregate` — recall/precision math, abstention/forbidden edge cases, None-exclusion |
| `tests/intelligence/test_router.py` | Unit (no DB) | H5 query router — `resolve_strategy` known/unknown shapes, `general` all-defaults, weight-merge semantics, top_k floor |
| `tests/intelligence/test_cross_relations.py` | Unit (no DB) | Cross-doc relation pass — (family, actor) pairing, same-doc exclusion, dedup, published_at direction (incl. permuted ingestion order), max_pairs cap, dry-run, LLM-error continuation |
| `tests/test_relations_cli.py` | Unit (no DB) | `nexus relations run` — help, pack-domain default, `--json` zero-count output |

Benchmark fixtures: [`evals/memory/nexus_synthetic/`](../evals/memory/nexus_synthetic/README.md). First live baseline: [`docs/benchmarks/baseline-2026-07-02.md`](benchmarks/baseline-2026-07-02.md). Router validation run (PR #26): [`docs/benchmarks/runs/router-t-r2/`](benchmarks/runs/router-t-r2/report.md). External benchmark (PR #29, H7): [LongMemEval fixtures](../evals/memory/longmemeval/README.md), [`tests/benchmarks/test_longmemeval_adapter.py`](../tests/benchmarks/test_longmemeval_adapter.py), report at [`docs/benchmarks/longmemeval-2026-07-04.md`](benchmarks/longmemeval-2026-07-04.md).

## Working Notes

- [Active iterations](iterations/active/)
- [Archived iterations](iterations/archive/)
- [Utility notes](utils/README.md)

## Source Drafts

- [Nexus PoC source draft](../proof_of_concept.md)
