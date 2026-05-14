# Testing

No executable application tests exist yet. Use this test strategy when implementation begins.

Read [docs/specs/operations.md](specs/operations.md) for phase-level validation gates.

## Required Test Types

- Unit tests for deterministic ingestion, cleaning, chunking, deduplication, and retrieval helpers.
- Database integration tests for persistence, foreign keys, and provenance invariants.
- Schema validation tests for LLM extraction and synthesis outputs.
- Worker tests for job orchestration and retry behavior.
- End-to-end fixture tests for ingesting a small source and producing spans, claims, and a grounded answer.

## Critical Invariants

- Clean documents retain source provenance.
- Span order is deterministic.
- Accepted claims have at least one support evidence link.
- Query answers cite retrieved evidence.
- Agent/model runs are logged with status and cost estimate.
