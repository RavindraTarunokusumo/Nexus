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

## Working Notes

- [Active iterations](iterations/active/)
- [Archived iterations](iterations/archive/)
- [Utility notes](utils/README.md)

## Source Drafts

- [Nexus PoC source draft](../proof_of_concept.md)
