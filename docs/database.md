# Database / Persistence

The MVP persistence target is PostgreSQL with pgvector.

Read [docs/specs/data-model.md](specs/data-model.md) for the full data model spec.

## MVP Tables

- `sources`
- `documents`
- `spans`
- `claims`
- `claim_evidence`
- `briefs`
- `brief_items`
- `agent_runs`

## Core Invariant

Accepted generated knowledge must preserve provenance:

```text
brief item -> claim -> span -> document/source
```

No accepted claim should exist without at least one supporting evidence span.
