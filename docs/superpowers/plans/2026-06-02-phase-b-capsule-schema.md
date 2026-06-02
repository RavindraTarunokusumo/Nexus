# Phase B — Capsule-Schema Foundation Plan

**Date:** 2026-06-02
**Branch:** `claude/phase-b-prep` (planning) → implementation branch TBD
**Status:** Planning output. Schema + backfill + legacy retirement only. No T2 judge wiring (Phase C). No retrieval (Phase D). No lifecycle workers (Phase E).

## Source documents

- `nexus_poc_v07_telos_semantic.md` — v0.7 PoC. §4.4 (Semantic Capsule), §7.1 (schema), §8 (pipeline tiers), §13 (lifecycle), §17 (open questions).
- `domain_pack_contract_v3_telos.md` — v3 domain pack contract.
- `docs/superpowers/specs/2026-05-29-ai-domain-pack-extraction-scheme-design.md` — v3 extraction-scheme spec.
- `docs/iterations/archive/2026-05-30-phase-a-telos-semantic-bridge.md` — Phase A archive, including the per-task commit hashes and the documented Phase B backlog.
- `docs/superpowers/plans/2026-05-30-telos-semantic-extraction-bridge.md` — Phase A plan (this doc's structural template).

---

## 1. Gap map — Phase A → Phase B promotion

Phase A landed every shape of the v0.7 object **in-memory**, with the full `SemanticObject.model_dump(mode="json")` stashed inside `Claim.entities_json["_v0_7"]` plus `_function` and `_domain_family` traceability keys ([projection.py:107-115](../../../app/intelligence/projection.py)). Phase B promotes those payloads to durable rows.

| Phase A artefact | Lives in | Phase B target |
|---|---|---|
| `SemanticObject.source_refs` | `Claim.entities_json["_v0_7"]["source_refs"]` | `capsule_segments(capsule_id, segment_id, role)` rows (one per ref) |
| `SemanticObject.core_type` | `Claim.entities_json["_v0_7"]["core_type"]` | `semantic_capsules.core_type` (CHECK-constrained TEXT) |
| `SemanticObject.text` / `original_text` | `Claim.entities_json["_v0_7"]["text"]` | `semantic_capsules.text` |
| `SemanticObject.domain_family` | `Claim.entities_json["_domain_family"]` | `semantic_capsules.object_family` |
| `SemanticObject.domain_object_type` | `Claim.entities_json["_v0_7"]["domain_object_type"]` | `semantic_capsules.domain_object_type` |
| `SemanticObject.function` | `Claim.entities_json["_function"]` | `semantic_capsules.function` |
| `SemanticObject.facets` | `Claim.entities_json["_v0_7"]["facets"]` + split into `entities_json` / `topics_json` | `semantic_capsules.facets` (JSONB, the canonical copy) |
| `SemanticObject.epistemic` | `Claim.entities_json["_v0_7"]["epistemic"]` | `semantic_capsules.epistemic_state` (JSONB) |
| `SemanticObject.salience` | `Claim.entities_json["_v0_7"]["salience"]` | `semantic_capsules.salience` (FLOAT) |
| `SemanticObject.mvp_claim_type` | `Claim.claim_type` (already projected) | left in `claims` only — projection bridge keeps it |
| pack telos string | not stored | `semantic_capsules.source_telos` (denormalised at write time) |
| domain identifier | `Source.domain_pack` | `semantic_capsules.domain` (snapshotted) |
| T-tier that emitted it | not stored | `semantic_capsules.created_by_tier` (`"t2"` for Phase B) |
| concrete model name | `AgentRun.model` | `semantic_capsules.created_by_model` (snapshotted) |
| embedding | not stored | `semantic_capsules.embedding` (VECTOR(384) via `bge-small-en-v1.5`, embedded at write time) |
| (none yet — Phase C) | n/a | `semantic_relations` rows |
| (none yet — Phase E) | n/a | `theses`, `decision_artefacts` rows |
| pack registry | YAML on disk; `app/domain_packs/{pack_id}.yaml` | `domain_packs` table (registry only; YAML stays source of truth) |

What Phase A explicitly did **not** do that Phase B does:
- Promote `_v0_7` blob to typed columns + a join table to spans.
- Backfill from existing rows (Phase A could not backfill — there was no destination).
- Replace `pack.metadata.supported_source_types[0]` profile fallback with real detection.
- Cut `app/evaluation/runner.py` over from `ExtractionOutput` to `SemanticExtractionOutput`; retire `ExtractedClaim`/`ExtractionOutput`; remove `app/intelligence/prompts/extract_claims.py` and the `schema_name="required"` correction path.

---

## 2. Strategy — schema + backfill + legacy retirement, in one PR series

Phase B is **scoped exactly to schema and dual-write**. It does **not** touch retrieval, the T2 judge, lifecycle, or pack inheritance. Justification:

- A migration that adds tables and a backfill that fills them is a self-contained, reviewable unit.
- The chat / `/chat/answer` retrieval path keeps reading from `claims` until Phase D rewires it. Splitting the work this way lets Phase B land independently — a single dual-write commit that doesn't change read-side behaviour.
- The Phase A `_v0_7` stash is purely forward-compat; until Phase B reads it, it's dead weight. Phase B is the payoff.
- Legacy schema removal (B5) lives in this phase because the eval runner is the **only** remaining consumer of `ExtractionOutput`. Porting it is a small mechanical change; bundling it with the migration is the right unit so the dual-path test surface (`tests/intelligence/test_a6_projection_regression.py`'s back-compat smoke at `tests/intelligence/test_semantic_object_schema.py:147-167`) dies in the same PR series as the schema it was protecting.

**Out of scope** (deferred phases):
- T2 judge wiring (Phase C). The Phase A `judge_semantic_object.py` prompt still has no `semantic_relations` destination after B1; wiring waits for C.
- Capsule retrieval (Phase D). `/chat/answer` keeps loading `active` claims.
- Lifecycle / consolidation workers (Phase E).
- Pack inheritance resolution (deferred; only the column is added — see §8 ADR Q4).
- Multi-domain packs (Phase F).

---

## 3. Phase B detailed task breakdown (5 sub-items, each one commit)

Per Workflow Rule 1, every sub-item lands as its own commit. Per the GitNexus rules, run `gitnexus_impact` on each edited symbol before touching it. These become the new `TODO.md` Phase B entries.

### B1 — Alembic migration 0005

- `app/db/migrations/versions/0005_semantic_capsules.py`: create six tables — `semantic_capsules`, `capsule_segments`, `semantic_relations`, `theses`, `decision_artefacts`, `domain_packs` — per the column-level schema in §4 below.
- `app/db/models.py`: add ORM models for the same six tables. Pin the `Vector(384)` import. Add `Document.capsules` and `Span.capsule_segments` `relationship` backrefs.
- New test `tests/db/test_capsules_migration.py`: upgrades 0004 → 0005, asserts every column / index / CHECK constraint / FK exists; downgrades back; round-trip a minimal insert via the ORM.
- Hooked into existing migration plumbing (`alembic upgrade head`). The pattern mirrors `tests/evaluation/test_migration_003.py`.
- **No application code reads or writes these tables yet** at the end of B1.

`gitnexus_impact` targets: none (new tables, new ORM classes, no callers).

### B2 — Dual-write from `projection.project()` + extraction graph

- Extend `ProjectedClaim` (or add a sibling `ProjectedCapsule` dataclass) so the projection layer emits everything `store_claims` needs to write both a `Claim` row and a `SemanticCapsule` row + N `CapsuleSegment` rows.
- `app/intelligence/extraction.py::store_claims` writes the capsule + capsule-segment rows in the **same transaction** as the existing `Claim` + `ClaimEvidence` writes. If either write fails, the whole document's extraction rolls back — capsules and claims must not diverge.
- Capsule `embedding` is generated at write time by the existing `app/intelligence/embedder.py` (`bge-small-en-v1.5`, 384 dims). One embedder load per extraction run, batched per document.
- `created_by_tier` is hard-coded `"t2"` (current production tier; A6 cut over to a single T2 call per span). `created_by_model` is read from the `AgentRun.model` column written by `complete_json`.
- `source_telos` is read from `pack.telos.primary_purpose` (or whatever scalar v3 calls "telos summary" — confirm against `app/domain_packs/loader.py::Telos` at implementation time) and snapshotted onto the row.
- New tests:
  - `tests/intelligence/test_capsules_dual_write.py` — DB-integration test (similar shape to `test_extraction_graph.py`): one fixture document, 1 span, fake LLM client returns 2 valid `SemanticObject`s, assert 2 capsules + 2 capsule_segments + 2 claims + 2 claim_evidence rows exist and reference the same `source_refs`.
  - Add a transactional-rollback case: monkey-patch a capsule write to raise, assert the matching `Claim` row also doesn't land (one-transaction invariant).
- Existing `/chat/answer` keeps reading `Claim`s — verify the existing chat tests still pass without modification.

`gitnexus_impact` targets: `store_claims`, `validate_and_project`, `project`. Expected: HIGH (extraction hot path), upstream callers are the extraction graph + tests only.

### B3 — Backfill from `_v0_7` blob

- New CLI command `nexus capsules backfill [--dry-run] [--limit N]` at `app/cli/capsules.py`, registered in `app/cli/main.py`.
- New module `app/intelligence/capsule_backfill.py`: iterate `Claim` rows where `entities_json ? '_v0_7'`, reconstruct the `SemanticObject` (Pydantic round-trip from the JSONB), look up source_id and document via the FK chain, write the capsule + capsule_segments. Idempotent via a `claim_id`→`capsule_id` deterministic UUID5 mapping (or an explicit `idempotency_key` column — see §4) so re-runs are no-ops.
- Embeddings: re-embed `SemanticObject.text` at backfill time via the same `bge-small-en-v1.5` embedder. NOT lazy — populating embeddings at write time keeps Phase D's retrieval contract simple (always-present non-null vector).
- `source_refs`: the `_v0_7` blob's `source_refs` are span IDs that already exist in `claim_evidence` for the same claim. Backfill verifies the join: for each `source_ref`, look up the matching `claim_evidence.span_id` and write `capsule_segments(capsule_id, segment_id=span_id, role=claim_evidence.evidence_role)`. If the span no longer exists (cascade-deleted document), skip the entire claim and log.
- `--dry-run` reports counts without writing.
- Tests: `tests/intelligence/test_capsule_backfill.py` — fixture of 3 hand-built claims with `_v0_7` payloads, assert backfill produces correct capsules + capsule_segments; assert re-running is idempotent (no duplicates); assert orphaned claims (missing `_v0_7`) are skipped; assert `--dry-run` writes nothing.

`gitnexus_impact` targets: none on production paths (new module, new CLI). On the ORM models — LOW.

### B4 — Ingestion-side v3 source-type profile detection

- Replace the `pack.metadata.supported_source_types[0]` fallback in [`extraction.py::_resolve_pack_and_source_type`](../../../app/intelligence/extraction.py) with a real classifier.
- **Approach selected:** URL-domain → profile heuristic table declared on the pack. The pack already declares a `source_type_profiles` map; B4 adds a `url_domain_hints: dict[str, str]` field on `SourceTypeProfile` (loader change) so `arxiv.org` → `arxiv_paper`, `techcrunch.com` / `theverge.com` → `ai_news_article`, etc. Fall-back chain: (1) match against `Document.url` + the `url_domain_hints` table; (2) regex over `Document.title` / `Source.name` (declared on the same profile, optional); (3) the existing `supported_source_types[0]` default.
- **Why this approach** (not a T1 classifier call): the v3 spec already encodes source-type identity at the URL level; a T1 LLM call would burn budget per source for a problem the YAML can solve declaratively. Phase G's T1 stack revisits this if heuristics prove insufficient.
- The pack rewrite to add `url_domain_hints` is part of this commit (a small targeted edit to `app/domain_packs/personal_ai_tech.yaml`).
- New unit test `tests/intelligence/test_resolve_pack_and_source_type.py` (closes the Phase A test-gap TODO too — see TODO.md cleanup §10): URL match, title regex match, fallback to default, empty `supported_source_types` (covered by the existing defensive branch from commit `d1e5cb6`).

`gitnexus_impact` targets: `_resolve_pack_and_source_type`. Expected: LOW — called only from `load_spans`. The blast radius is the extraction graph; behaviour change is a different `v3_source_type` selected for some inputs, which affects budget / prompt content but not data shape.

### B5 — Eval-runner port + legacy schema retirement

This commit is the dual-path teardown. **All of these happen in one commit so the legacy and new schemas never coexist on `main` without a consumer in flight.**

1. Port `app/evaluation/runner.py` from `ExtractionOutput` to `SemanticExtractionOutput`. The `ClaimExtractionJudge` is renamed (or supplemented) to score against `SemanticObject` rather than `ExtractedClaim`. Concretely: judge metrics become `mvp_claim_type_projection_accuracy`, `core_type_validity`, `domain_family_validity`, plus a `capsule_completeness` rubric on facets / epistemic / salience.
2. Migrate `evals/gold/claim_extraction/ai_tech_v1.yaml` → `evals/gold/semantic_objects/ai_tech_v3.yaml`. The new file uses the `SemanticObject` schema (gold = full objects, not just claims). NOTE: the Phase A plan referenced `ai_tech_v2.yaml`, but only `v1.yaml` exists on disk; B5 renames to `v3.yaml` to match the v3 pack contract.
3. Update `tests/evaluation/test_runner.py` to construct `SemanticExtractionOutput` rather than `ExtractionOutput` mocks.
4. Delete `app/intelligence/prompts/extract_claims.py` (the legacy claim-only prompt). The `schema_name="required"` correction-prompt path in `app/intelligence/prompts/_shared.py` becomes unused and is removed at the same time.
5. Delete `ExtractedClaim` and `ExtractionOutput` from `app/intelligence/llm_client.py`. Update the docstring at line 178-184 to reflect the cutover.
6. Delete the back-compat smoke test at `tests/intelligence/test_semantic_object_schema.py:147-167` (the "Legacy ExtractedClaim / ExtractionOutput still parse" block).
7. Update `tests/test_llm_client.py` mocks that reference `ExtractionOutput` (lines 203, 223, 242, 261) to use `SemanticExtractionOutput`.
8. Eval framework's first object-level run produces metrics for `mvp_claim_type_projection_accuracy` and at least one capsule-only metric (e.g. `core_type_validity`).

`gitnexus_impact` targets: `execute_run`, `ClaimExtractionJudge`, plus `ExtractedClaim` / `ExtractionOutput` as symbols. Expected: MEDIUM. Upstream callers: the eval CLI (`app/cli/eval.py`), `tests/evaluation/*`, `tests/test_llm_client.py`.

---

## 4. Schema decisions — column-level

Where v0.7 §7.1 is ambiguous, the decision is explicit and justified.

### 4.1 `semantic_capsules`

```sql
CREATE TABLE semantic_capsules (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id        UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    document_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,  -- Phase B addition: denormalised for cheap document-scoped queries
    claim_id         UUID NULL     REFERENCES claims(id)   ON DELETE SET NULL,  -- Phase B-only dual-write bridge; set to NULL when Phase D retires claims
    idempotency_key  TEXT NOT NULL UNIQUE,                                      -- "{document_id}:{span_id_sorted_csv}:{core_type}:{sha1(text)[:8]}" so re-extraction + backfill is idempotent
    core_type        TEXT NOT NULL CHECK (core_type IN (
                       'claim','event','observation','result','risk','argument',
                       'explanation','comparison','definition','constraint',
                       'question','description','state_change',
                       'narrative_development','other')),
    text             TEXT NOT NULL,
    domain           TEXT NOT NULL,
    source_telos     TEXT NULL,
    object_family    TEXT NOT NULL,
    domain_object_type TEXT NOT NULL,
    function         TEXT NULL,
    facets           JSONB NOT NULL DEFAULT '{}',
    epistemic_state  JSONB NOT NULL DEFAULT '{}',
    salience         FLOAT NOT NULL DEFAULT 0.5 CHECK (salience BETWEEN 0 AND 1),
    confidence       FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    lifecycle_state  TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle_state IN (
                       'candidate','active','confirmed','qualified',
                       'contradicted','superseded','stale','archived','rejected')),
    escalation_state TEXT NOT NULL DEFAULT 'none' CHECK (escalation_state IN (
                       'none','flagged','escalated','resolved')),
    embedding        VECTOR(384) NULL,
    created_by_tier  TEXT NOT NULL CHECK (created_by_tier IN ('t0','t1','t2','t3','t4','backfill')),
    created_by_model TEXT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_semantic_capsules_source_id   ON semantic_capsules(source_id);
CREATE INDEX ix_semantic_capsules_document_id ON semantic_capsules(document_id);
CREATE INDEX ix_semantic_capsules_claim_id    ON semantic_capsules(claim_id) WHERE claim_id IS NOT NULL;
-- No pgvector index in Phase B (retrieval lands in Phase D; HNSW is added there).
-- No (domain, lifecycle_state) index in Phase B (no consumer until Phase D/E).
```

**Decisions and rationale:**
- **`core_type` as TEXT + CHECK** (not a Postgres ENUM). v0.7 §3.2 enumerates 15 core types but the contract permits future domains to introduce additions; CHECK is cheap to evolve via `ALTER TABLE ... DROP CONSTRAINT / ADD CONSTRAINT`, whereas Postgres ENUM types require `ALTER TYPE ... ADD VALUE` which is non-transactional in some contexts. The `lifecycle_state` and `escalation_state` columns use the same pattern for the same reason.
- **`source_refs` is NOT a column on `semantic_capsules`.** v0.7 §7.1 declares both `source_refs JSONB` on the capsule AND a `capsule_segments` join table; we keep only the join table as the single source of truth. The Pydantic `SemanticObject.source_refs` list is denormalised into N `capsule_segments` rows at write time, not duplicated on the capsule row. Rationale: a JSONB list of UUIDs is harder to query, can't be FK-constrained, and creates a drift risk if backfill regenerates one but not the other.
- **`embedding` is `VECTOR(384)` NULL** with the same dimensions as `spans.embedding` ([models.py:85](../../../app/db/models.py)). Phase D's hybrid retrieval will join capsules-to-spans on similar vector space without dimension translation. NULL is permitted but in practice the dual-write and backfill paths always populate it; future T0/T1 lower-confidence captures might intentionally skip embedding generation.
- **`facets` / `epistemic_state` as JSONB, validated at write time via Pydantic round-trip.** The ORM layer constructs `SemanticObject` from the row at read time, raising on shape drift — this is the same pattern Phase A uses for the `_v0_7` stash. Read-time validation alone is too lax (lets schema drift land silently); write-time-only validation is too rigid (blocks ad-hoc backfill scripts). Both.
- **`idempotency_key` column** is the deduplication mechanism for backfill (B3) and for re-extraction of the same document. Without it, a re-run of the extraction graph against the same document creates duplicate capsules. The key shape is `"{document_id}:{sorted_span_csv}:{core_type}:{sha1(text)[:8]}"` — stable across runs, varies on meaningful re-extraction.
- **`claim_id` is a soft FK with `ON DELETE SET NULL`**, not `CASCADE`. Phase D will retire the `claims` table; we don't want the capsule rows to vanish when claims are dropped. During Phase B's dual-write window, `claim_id` is always populated.
- **Indexes added in Phase B are only the ones B2 and B3 hot paths need.** `source_id`, `document_id`, `claim_id` (partial). No HNSW, no `(domain, lifecycle_state)`, no `(object_family, domain_object_type)` — those land in Phase D when retrieval needs them. Adding indexes without consumers wastes write throughput.

### 4.2 `capsule_segments`

```sql
CREATE TABLE capsule_segments (
    capsule_id UUID NOT NULL REFERENCES semantic_capsules(id) ON DELETE CASCADE,
    segment_id UUID NOT NULL REFERENCES spans(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'grounds' CHECK (role IN (
       'grounds','supports','contradicts','qualifies','refines','exemplifies','other')),
    PRIMARY KEY (capsule_id, segment_id)
);

CREATE INDEX ix_capsule_segments_segment_id ON capsule_segments(segment_id);  -- reverse lookup: "which capsules reference this span?"
```

**Decisions:**
- **`segment_id` FKs `spans.id`** — Phase B keeps the v0.6 column name `spans`. v0.7 renames it to `segments`; that rename is **explicitly deferred** (Phase F or later, alongside the multi-domain rename pass). The FK target is the existing table; the table name is unchanged in this PR.
- **`role` CHECK constraint** matches the existing `claim_evidence.evidence_role` vocabulary so backfill can preserve roles 1:1.
- **No surrogate `id`** — the `(capsule_id, segment_id)` composite is the PK; this matches v0.7 §7.1.

### 4.3 `semantic_relations`

```sql
CREATE TABLE semantic_relations (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_capsule_id     UUID NOT NULL REFERENCES semantic_capsules(id) ON DELETE CASCADE,
    target_capsule_id     UUID NULL     REFERENCES semantic_capsules(id) ON DELETE CASCADE,
    target_thesis_id      UUID NULL     REFERENCES theses(id) ON DELETE CASCADE,
    relation_type         TEXT NOT NULL CHECK (relation_type IN (
                            'supports','contradicts','refines','exemplifies',
                            'qualifies','supersedes','depends_on','other')),
    domain_relation_type  TEXT NULL,
    polarity              TEXT NULL CHECK (polarity IN ('positive','negative','neutral') OR polarity IS NULL),
    strength              FLOAT NOT NULL DEFAULT 0.5 CHECK (strength BETWEEN 0 AND 1),
    confidence            FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    evidence_capsule_ids  UUID[] NOT NULL DEFAULT '{}',
    rationale             TEXT NULL,
    epistemic_state       JSONB NOT NULL DEFAULT '{}',
    created_by_tier       TEXT NOT NULL CHECK (created_by_tier IN ('t1','t2','t3','t4')),
    created_by_model      TEXT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (target_capsule_id IS NOT NULL OR target_thesis_id IS NOT NULL)
);

CREATE INDEX ix_semantic_relations_source ON semantic_relations(source_capsule_id);
CREATE INDEX ix_semantic_relations_target_capsule ON semantic_relations(target_capsule_id) WHERE target_capsule_id IS NOT NULL;
CREATE INDEX ix_semantic_relations_target_thesis ON semantic_relations(target_thesis_id)   WHERE target_thesis_id  IS NOT NULL;
```

**Decisions:**
- Table is created in B1 but **has no writer in Phase B**. Phase C (T2 judge wiring) is its first writer.
- The XOR constraint (`target_capsule_id` OR `target_thesis_id`) enforces v0.7 §10's intent: a relation always targets a capsule or a thesis, never neither.
- `evidence_capsule_ids` as `UUID[]` matches v0.7 §7.1 verbatim. Phase B does not introduce a join table here; the array is small (typically 1-3 entries) and indexes aren't needed in B.

### 4.4 `theses`

```sql
CREATE TABLE theses (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain                      TEXT NOT NULL,
    thesis_type                 TEXT NOT NULL,
    title                       TEXT NULL,
    statement                   TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'active',
    confidence                  FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    scope                       JSONB NOT NULL DEFAULT '{}',
    invalidation_criteria       JSONB NOT NULL DEFAULT '[]',
    supporting_capsule_ids      UUID[] NOT NULL DEFAULT '{}',
    contradicting_capsule_ids   UUID[] NOT NULL DEFAULT '{}',
    epistemic_state             JSONB NOT NULL DEFAULT '{}',
    lifecycle_state             TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle_state IN (
                                  'candidate','active','confirmed','qualified',
                                  'contradicted','superseded','stale','archived','rejected')),
    created_by_tier             TEXT NOT NULL CHECK (created_by_tier IN ('t2','t3','t4')),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_theses_domain ON theses(domain);
```

**Decisions:** schema-only in B1; first writer is Phase E (consolidation worker).

### 4.5 `decision_artefacts`

```sql
CREATE TABLE decision_artefacts (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artefact_type         TEXT NOT NULL,
    domain                TEXT NULL,
    question              TEXT NULL,
    answer                TEXT NULL,
    linked_thesis_ids     UUID[] NOT NULL DEFAULT '{}',
    linked_capsule_ids    UUID[] NOT NULL DEFAULT '{}',
    source_refs           JSONB NOT NULL DEFAULT '[]',
    epistemic_state       JSONB NOT NULL DEFAULT '{}',
    created_by_tier       TEXT NOT NULL CHECK (created_by_tier IN ('t2','t3','t4')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Decisions:** schema-only in B1; first writer is Phase E or F. `source_refs JSONB` is kept here (no join table) because decision_artefacts often reference external sources (URLs, document anchors) that aren't necessarily capsules — the JSONB shape stays open.

### 4.6 `domain_packs`

```sql
CREATE TABLE domain_packs (
    id              TEXT PRIMARY KEY,                    -- e.g. 'personal_ai_tech'; matches the YAML filename without extension
    version         TEXT NOT NULL,
    domain          TEXT NOT NULL,
    source_types    TEXT[] NOT NULL DEFAULT '{}',
    parent_pack_id  TEXT NULL REFERENCES domain_packs(id) ON DELETE SET NULL,  -- ADR Q4: column added, resolution logic deferred
    pack_json       JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Decisions:**
- **YAML files at `app/domain_packs/{pack_id}.yaml` remain the source of truth.** The `domain_packs` table is a *registry* — Phase B writes one row per pack from the loader on startup so other DB consumers (e.g. Phase E lifecycle workers) can join against `pack_json` without re-parsing YAML. The loader's `lru_cache` is untouched; this table is downstream, not upstream.
- A startup hook (or a one-shot CLI `nexus packs register`) seeds the table from disk in B1. Implementation: a small `app/domain_packs/registry.py` module that takes a `DomainPack` and upserts.
- `parent_pack_id` is added but the loader does NOT resolve inheritance in Phase B. See §8 ADR Q4.

---

## 5. Migration strategy — when does the legacy schema die?

The legacy `claims` and `claim_evidence` tables **do not go away in Phase B**. Phase B is **dual-write**, not dual-read.

Invariant during Phase B:
```
extraction → projection → (Claim + ClaimEvidence) AND (SemanticCapsule + CapsuleSegment)
chat / /chat/answer        → reads Claim rows (unchanged)
eval framework             → ports to SemanticExtractionOutput (B5), reads SemanticObject (not Claims)
backfill (B3)              → reads existing _v0_7 stash, writes SemanticCapsule
```

Legacy schema is retired in **Phase D** (retrieval over capsules), after `/chat/answer` is ported. That is explicitly NOT this PR. Phase B writes capsules into shadow; Phase D promotes them to the read path; the `claims` table is dropped only when no production reader remains.

**Phase B's last commit (B5) IS the legacy removal — but only for the in-memory schema (`ExtractedClaim`/`ExtractionOutput`).** The DB tables `claims` and `claim_evidence` survive Phase B; only the legacy Pydantic types die.

---

## 6. Backfill mapping — every column to its data source

For each existing `Claim` row where `entities_json ? '_v0_7'`:

| `semantic_capsules` column | Backfill source |
|---|---|
| `id` | `uuid5(NAMESPACE_OID, idempotency_key)` for deterministic re-runs |
| `source_id` | `Claim.document_id` → `Document.source_id` (one extra join) |
| `document_id` | `Claim.document_id` |
| `claim_id` | `Claim.id` |
| `idempotency_key` | `"{document_id}:{sorted(source_refs)_csv}:{core_type}:{sha1(text)[:8]}"` |
| `core_type` | `entities_json["_v0_7"]["core_type"]` |
| `text` | `entities_json["_v0_7"]["text"]` (or `original_text` if present; mirror what `project()` chose) |
| `domain` | `Source.domain_pack` via `Document.source_id` |
| `source_telos` | Looked up at backfill time from `load_pack(domain).telos.primary_purpose`. NULL if the pack has no scalar telos string. |
| `object_family` | `entities_json["_v0_7"]["domain_family"]` (mirrored as `_domain_family` in Phase A, but the canonical source is the `_v0_7` blob) |
| `domain_object_type` | `entities_json["_v0_7"]["domain_object_type"]` |
| `function` | `entities_json["_v0_7"]["function"]` |
| `facets` | `entities_json["_v0_7"]["facets"]` verbatim |
| `epistemic_state` | `entities_json["_v0_7"]["epistemic"]` verbatim |
| `salience` | `entities_json["_v0_7"]["salience"]` |
| `confidence` | `entities_json["_v0_7"]["epistemic"]["confidence"]` (mirror of `Claim.confidence`) |
| `lifecycle_state` | `Claim.status == "active"` → `"active"`; `Claim.status == "rejected"` → `"rejected"`; otherwise `"active"`. |
| `escalation_state` | `entities_json["_v0_7"]["epistemic"]["needs_escalation"]` → `"flagged"` if True, else `"none"`. |
| `embedding` | **Re-embedded at backfill time** via `bge-small-en-v1.5(text)`. NOT lazy. |
| `created_by_tier` | Constant `"backfill"` — distinguishable from production T2-emitted rows. |
| `created_by_model` | Looked up via `AgentRun` rows for the same `(document_id, span_id)` — pick the most recent T2 run's `model`. NULL if not findable. |
| `created_at` | `Claim.created_at` |
| `updated_at` | `Claim.created_at` |

For each `ClaimEvidence` row tied to the Claim: one `capsule_segments(capsule_id, segment_id=span_id, role=evidence_role)` row.

**Columns backfill cannot fully populate:**
- `source_telos` may be NULL if the pack lacks a scalar telos summary (current `personal_ai_tech.yaml` likely does — confirm at implementation time; if so, falls back to `pack.metadata.name`).
- `created_by_model` may be NULL if the matching `AgentRun` is older than the audit-row introduction or was pruned.

Both fields tolerate NULL by design.

---

## 7. Capsule embeddings during dual-write

- Use the existing `app/intelligence/embedder.py::Embedder` (BAAI/bge-small-en-v1.5, 384 dims, L2-normalised). Same instance the ingestion pipeline already uses to embed spans — confirmed at `app/intelligence/embedder.py:8`.
- One embedder load per extraction run (cached at module level via the existing pattern; warm after the first span). Each `store_claims` invocation batches all of a document's capsules into one `embedder.encode(list_of_texts)` call.
- Backfill (B3) uses the same embedder, batched per claim chunk (configurable, default 64).
- Dimensions match `spans.embedding` so Phase D's hybrid retrieval can join capsules-to-spans in the same vector space without dimension translation.

---

## 8. ADR — Open Questions Q1 and Q4 from v0.7 §17

### Q1 — `SemanticCapsule` vs `Insight` / `Object` / `Evidence Unit`

**Decision: keep `SemanticCapsule` for engineering surface; defer external user-facing naming to Phase D's UI work.**

Phase A already chose:
- Python class: `SemanticObject` ([llm_client.py:214](../../../app/intelligence/llm_client.py))
- Table name (B1): `semantic_capsules`
- Field names externally exposed via API: not yet — A6 didn't add any public capsule endpoints.

**Phase B fixes these to:**
- DB table: `semantic_capsules` (matches v0.7 §7.1 verbatim).
- Python class for the in-memory shape: `SemanticObject` (Phase A's choice — keep).
- Python class for the ORM row: `SemanticCapsule` (Phase B introduces).
- Internal traceability keys in claims `entities_json`: stay `_v0_7`, `_function`, `_domain_family`.

External / API / UI naming is NOT decided in Phase B because Phase B exposes no new public endpoints. When Phase D builds the chat UI, the surface vocabulary can use `insight` or `evidence` for end-users if user research warrants — but engineering / SQL / Python types stay on `SemanticCapsule` / `SemanticObject`. Pin: the `claudemd` / project docs use **capsule** as the canonical noun; future PRs do not bikeshed.

Rationale:
- "Insight" suggests post-synthesis (theses are insights; capsules are upstream). Wrong altitude.
- "Object" is generic and collides with `SemanticObject` (the in-memory Pydantic class).
- "Evidence Unit" misrepresents the model — capsules are *units of meaning*, not *units of evidence*; evidence is the `capsule_segments` join.
- "Capsule" is awkward in user-facing copy but precise internally. The external-surface tradeoff lives in Phase D.

### Q4 — Pack inheritance

**Decision: add the column, defer the logic.**

`domain_packs.parent_pack_id` is added as a nullable self-FK in B1 (§4.6). The loader (`app/domain_packs/loader.py`) does **not** implement parent-pack resolution in Phase B. The YAML schema does not gain an `inherits_from` field in Phase B.

Rationale:
- Phase B is single-domain (`personal_ai_tech` only). There is no second pack to inherit from until Phase F.
- Adding the column now means Phase F doesn't need another migration.
- Implementing resolution now without a consumer is dead code that will rot.

When Phase F lands `sec_filing_v1` + `scientific_paper_v1`, that PR adds:
- `inherits_from` field in the YAML loader (`Metadata.inherits_from: str | None`)
- A resolution pass in `load_pack` that merges parent + child via deep-merge with child-wins semantics
- The corresponding `domain_packs.parent_pack_id` writes via the registry

Until then, every row has `parent_pack_id IS NULL`.

---

## 9. Test plan per sub-item

| Sub-item | Tests added |
|---|---|
| **B1** | `tests/db/test_capsules_migration.py` — upgrade 0004→0005; assert tables / columns / indexes / CHECK constraints / FKs; downgrade; ORM round-trip on each table. |
| **B2** | `tests/intelligence/test_capsules_dual_write.py` — DB-integration: 1 document, fake LLM returns N `SemanticObject`s, assert N capsules + M capsule_segments + N claims + M claim_evidence with consistent `source_refs`. Transactional-rollback test: capsule-write failure aborts the matching claim. |
| **B3** | `tests/intelligence/test_capsule_backfill.py` — backfill correctness, idempotency on re-run, skip-claims-without-`_v0_7`, `--dry-run` writes nothing, orphaned-span (cascade-deleted) skip + log. CLI smoke via Typer's `CliRunner`. |
| **B4** | `tests/intelligence/test_resolve_pack_and_source_type.py` — URL-domain match, title regex match, fallback to `supported_source_types[0]`, empty `supported_source_types` fallback (existing). Closes the Phase A test-gap TODO. |
| **B5** | Update `tests/evaluation/test_runner.py` to construct `SemanticExtractionOutput`. Update `tests/test_llm_client.py` lines 203/223/242/261. Delete `tests/intelligence/test_semantic_object_schema.py:147-167`. New `evals/gold/semantic_objects/ai_tech_v3.yaml` covering ≥10 examples spanning ≥5 `core_type` values. Verify `nexus eval run` produces non-NULL `mvp_claim_type_projection_accuracy` + `core_type_validity`. |

Beyond per-sub-item tests:
- The Phase A regression test `tests/intelligence/test_a6_projection_regression.py` continues to pass without modification — it exercises projection in isolation, which is unchanged.
- All existing `tests/evaluation/*` and `tests/test_extraction_graph.py` pass (B5 updates the runner, but the eval graph shape is preserved).

---

## 10. Pre-PR gates

- **`/simplify`** — required (Phase A standard).
- **`doc-updater`** — required. Touches `docs/database.md` (new tables), `docs/architecture.md` (capsule layer + dual-write), `docs/patterns.md` (idempotency-key pattern), `docs/cli.md` (`nexus capsules backfill`), `docs/testing.md` (new test modules).
- **`security-review`** — **justified.** Two surfaces:
  1. The migration adds JSONB columns (`facets`, `epistemic_state`, `scope`, `invalidation_criteria`) that ingest user-derived content. Confirm Pydantic round-trip validation at write time (not just read time) so malformed payloads can't corrupt downstream queries.
  2. The backfill (B3) reads the `_v0_7` JSONB blob, which is Pydantic-validated at A5 write time but has been at rest in the DB since — re-validate on read before writing to typed columns, in case anyone hand-edited it.
- **`test-plan-writer`** — **justified.** A migration + dual-write + backfill + legacy retirement is the largest single-PR surface change since Phase A; a formal written test plan de-risks the cutover.

---

## 11. Phase B success criteria

A successful Phase B PR series ends with:
1. `alembic upgrade head` runs cleanly on a fresh database and on a Phase A database.
2. Every Phase-A-emitted `Claim` row with a `_v0_7` blob has a corresponding `semantic_capsules` row + `capsule_segments` rows linkable back to spans. Backfill is idempotent on re-run.
3. `/chat/answer` and `/chat/sessions/...` continue to work unchanged. The chat tests pass with no modification.
4. `tests/intelligence/test_a6_projection_regression.py` passes (Phase A invariant).
5. `tests/db/test_capsules_migration.py` + `tests/intelligence/test_capsules_dual_write.py` + `tests/intelligence/test_capsule_backfill.py` + `tests/intelligence/test_resolve_pack_and_source_type.py` are green.
6. `ExtractedClaim` / `ExtractionOutput` / `app/intelligence/prompts/extract_claims.py` are deleted from the tree. `grep -r 'ExtractedClaim\|ExtractionOutput' app/ tests/` returns zero hits.
7. `nexus eval run` produces a result with non-NULL `mvp_claim_type_projection_accuracy` and at least one capsule-only metric (`core_type_validity`).
8. `docs/iterations/archive/2026-XX-XX-phase-b-capsule-schema.md` is written and commit hashes are attached to each B-item.

---

## 12. Open questions for human review

These are calls the plan makes that warrant explicit human sign-off before B1 starts:

1. **`source_telos` source field on the pack.** The loader exposes `Telos.primary_purpose` and several related fields ([loader.py:Telos](../../../app/domain_packs/loader.py)). Phase B picks `primary_purpose` as the snapshot string. If the user prefers a composite (e.g. `f"{primary_purpose} | {secondary_purposes[0]}"`), say so before B2.
2. **`core_type` constraint mechanism.** Plan chooses CHECK over Postgres ENUM. If migration ergonomics aren't a concern and you'd rather have ENUM's type safety at the DB level, flag this before B1.
3. **Backfill `created_by_model` lookup strategy.** The plan joins `AgentRun` by `(document_id, span_id)` and picks the most recent. If multiple T2 calls per span are expected, "most recent" might be wrong — clarify ordering preference (most recent vs. earliest succeeded vs. one per claim via the `run_id` already stored on the claim — but the current `Claim` model has no `run_id` column).
4. **Eval gold renaming v1 → v3.** Phase A plan said "v2 → v3", but only `ai_tech_v1.yaml` exists. The plan renames `v1` → `v3` to match the v3 pack contract. If you'd rather keep both for a deprecation window, say so before B5.
5. **External naming (Q1).** Plan defers to Phase D. If you want to fix `insight` vs `capsule` for end-user copy now, say so.
