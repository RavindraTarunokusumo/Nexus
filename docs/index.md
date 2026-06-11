# Docs Index

This repository is bootstrapped with an agent harness and supporting docs. Use this index as the starting point for repo-specific context.

## Core Docs

- [AGENTS.md](../AGENTS.md)
- [Agent Harness](agent-harness.md)
- [Project Specs](specs/README.md)
- [Architecture](architecture.md)
- [Database](database.md)
- [Patterns](patterns.md)
- [Testing](testing.md)
- [Commands](commands.md)
- [Nexus CLI](cli.md)
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
| `chat_answer.py` | Chat answer prompt; question/context builder for grounded single-turn and session answers |

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
| `tests/test_validation_harness.py` | Integration (`@pytest.mark.slow`) | End-to-end: text/RSS ingest, status, document inspection, semantic search |

## Working Notes

- [Active iterations](iterations/active/)
- [Archived iterations](iterations/archive/)
- [Utility notes](utils/README.md)

## Source Drafts

- [Nexus PoC source draft](../proof_of_concept.md)
