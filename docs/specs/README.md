# Nexus Project Specs

These specs convert the raw project drafts into implementation-facing documents.

## Source Documents

- `nexus_full_mvp_spec_markdown.md`: Nexus Lite MVP scope.
- `proof_of_concept.md`: broader Nexus PoC architecture and long-term system design.

## Spec Set

- [Nexus Lite MVP Spec](nexus-lite-mvp.md): canonical MVP entrypoint.
- [Product Spec](product.md): goals, scope, non-goals, users, success criteria.
- [Architecture Spec](architecture.md): system boundaries, runtime architecture, data flow, and phased growth.
- [Data Model Spec](data-model.md): persistence model, provenance rules, schema layers, lifecycle tiers.
- [Pipeline Spec](pipeline.md): ingestion, span creation, embeddings, extraction, retrieval, synthesis, automation.
- [API Spec](api.md): MVP REST endpoints, request/response contracts, and behavior rules.
- [Domain Pack Spec](domain-packs.md): domain adapter contract and initial personal AI/tech pack.
- [Operations Spec](operations.md): deployment, security, observability, costs, validation, and roadmap.

## Current Implementation Target

The first build target is **Nexus Lite**, a private VPS-hosted MVP that proves the loop:

```text
ingest -> structure -> extract -> retrieve -> synthesize -> answer
```

The broader Nexus PoC features remain design constraints, not required MVP scope, unless a later plan explicitly promotes them.
