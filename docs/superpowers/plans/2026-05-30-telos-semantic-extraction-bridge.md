# Telos-Semantic Extraction Bridge — Step 4 Implementation Plan

**Date:** 2026-05-30
**Branch:** `claude/determined-noether-93dc4a`
**Status:** Planning output only — NOT yet committed (Step 5 deferred per user).

## Source documents

- `nexus_poc_v07_telos_semantic.md` (v0.7) — telos-based semantic ontology, purpose-grammar packs, T0–T4 routing. Supersedes the v0.6 `proof_of_concept.md` on disk.
- `domain_pack_contract_v3_telos.md` (v3) — purpose-grammar pack contract (18 capabilities + minimal MVP subset).
- `docs/superpowers/specs/2026-05-29-ai-domain-pack-extraction-scheme-design.md` — AI-domain extraction scheme. **Lives on the unmerged `codex/ai-domain-extraction-spec` branch, not on `main`.** It defines the *scheme*; it explicitly excludes the *implementation plan, task breakdown, and migration design* — which is exactly what this document supplies.

---

## 1. Gap map — v0.7/v3 target vs. current codebase

| Concern | v0.7 / v3 target | Current code | Gap size |
|---|---|---|---|
| Foundational unit | **Semantic Capsule/Object**: `core_type` + `domain_family` + `domain_object_type` + `function` + `facets` + `epistemic_state` + `salience` + `lifecycle_state` | `Claim`: `claim_text`, `claim_type` (11 `Literal`s), `entities_json`, `topics_json`, `confidence`, `status` (`active`/`rejected`) — [models.py:94](app/db/models.py:94) | **Large** |
| Domain pack | Purpose grammar: telos, source-type profiles, semantic-object families, salience policy, facet policy, relation grammar, epistemic policy, model routing, budgets, retention, retrieval/context-assembly | `personal_ai_tech.yaml`: `topics`, `claim_types`, `brief_sections`, `models`. **Not loaded by any runtime code** — `claim_types` is hardcoded as `ClaimType` `Literal` in [llm_client.py:149](app/intelligence/llm_client.py:149) | **Large** (pack is dead config) |
| Extraction | Telos-aware, salience-gated semantic compression; candidate (T1) → judgment (T2) | Single-pass per-span claim extraction, T2 only; per-span concurrency w/ correction retry — [extraction.py](app/intelligence/extraction.py) | **Medium** |
| Evidence path | capsule → segment → source; `capsule_segments(role)` | claim → `claim_evidence(role)` → span → document | **Small** (maps cleanly; rename span↔segment) |
| Semantic relations | `semantic_relations` (supports/contradicts/refines/… + domain relations) | None | **Large** |
| Epistemic state | status, source_authority, confidence, evidence_quality, uncertainty, needs_escalation | only flat `confidence` | **Medium** |
| Lifecycle | candidate→active→confirmed→qualified→contradicted→superseded→stale→archived→rejected | `status` ∈ {active, rejected} | **Medium** |
| Model tiers | T0 deterministic, T1 cheap candidates, T2 judgment, T3 synthesis, T4 audit | T1 embed (local), T2 extract+chat, T3 = eval judge stub | **Medium** |
| Schema tables | `semantic_capsules`, `capsule_segments`, `semantic_relations`, `domain_packs`, `theses`, `decision_artefacts` | `claims`, `claim_evidence`, `spans`, `briefs` (empty) | **Large** |
| Retrieval | telos-aware over capsules; domain-pack hybrid weights; intent classification | vector span search + load active claims ([chat.py]) | **Medium** |
| Eval | object-schema-validity, salience precision/recall, relation accuracy, epistemic/escalation, MVP-projection accuracy | `ClaimExtractionJudge` only | **Medium** |

---

## 2. Strategy — two-layer bridge (recommended)

The v0.7 roadmap (Sprint 0) and a literal v3 read both imply a big-bang `semantic_capsules` migration. The extraction-scheme spec instead recommends a **two-layer bridge**, and that is the recommended path here because it:

- keeps the existing API, chat, and eval harness working (chat reads `active` claims; eval scores claims);
- delivers the highest-value change first — bringing the domain pack to life as a real purpose grammar and improving extraction semantics;
- defers the risky schema migration until the extraction layer is proven.

**Layer 1 (canonical):** extract v0.7 semantic objects in-memory, telos-/salience-guided, schema-validated, evidence-path-enforced.
**Layer 2 (projection):** project each accepted object into the existing `claims` + `claim_evidence` tables via `mvp_claim_type`, stashing the full v0.7 object as forward-compat metadata.

This session's **Step 4 = Phase A** (the bridge, no migration). **Phase B** (the `semantic_capsules` schema + relations + capsule retrieval) is outlined for a follow-up session.

---

## 3. Phase A — detailed task breakdown (each sub-item = one commit)

> Per Workflow Rule 1, every sub-item lands as its own commit. Per the GitNexus rules, run `gitnexus_impact` on each edited symbol before touching it (impacted symbols flagged inline). These become the `TODO.md` entries in Step 4.

### A0 — Bring the extraction-scheme spec onto this branch
- Copy `2026-05-29-ai-domain-pack-extraction-scheme-design.md` into `docs/superpowers/specs/` on this branch (it currently exists only on `codex/ai-domain-extraction-spec`). Reference it from `docs/specs/domain-packs.md`.
- *Rationale:* the plan depends on it; it must be on `main` to be authoritative.

### A1 — Domain pack schema + loader
- New `app/domain_packs/loader.py`: Pydantic models mirroring the v3 minimal-MVP subset — `metadata`, `telos`, `source_type_profiles`, `semantic_object_families` (with `object_types`, `core_type_mapping`, `mvp_claim_type` per type, `required_fields`), `salience_policy`, `facet_policy`, `relation_grammar`, `epistemic_policy`, `model_routing_policy`, `budgets`, `retention_policy`, `retrieval_policy`, `context_assembly`, `evaluation_contract`.
- `load_pack(pack_id: str) -> DomainPack` reads `app/domain_packs/{pack_id}.yaml`, validates, `@lru_cache`.
- Unit tests: valid load, missing file, schema-invalid pack.
- *Impact:* new module, no callers yet — zero blast radius.

### A2 — Author `personal_ai_tech.yaml` v3
- Rewrite the pack from the extraction-scheme spec: AI telos (primary/secondary/anti-purposes, reader goals), the 9 source-type profiles, the 10 semantic-object families with `object_types` + `core_type_mapping` + `mvp_claim_type`, salience policy, AI facet list, relation grammar, epistemic policy, T0–T4 routing, per-source budgets, retention windows, retrieval intents + hybrid weights, context-assembly order, evaluation contract.
- Validate it loads via A1's loader (add a test that loads the real file).
- Keep the existing top-level `claim_types`/`brief_sections`/`models` keys for back-compat until projection is wired.

### A3 — Semantic-object extraction schema
- In `app/intelligence/llm_client.py`: add `EpistemicState`, `SemanticObject` (`source_refs`, `core_type`, `domain_family`, `domain_object_type`, `function`, `text`, `original_text`, `facets: dict`, `epistemic: EpistemicState`, `salience: float`, `mvp_claim_type: ClaimType`) and `SemanticExtractionOutput`. `core_type` as `Literal` matching v0.7 core types.
- Keep `ExtractedClaim`/`ExtractionOutput` until A6 cuts over, then remove.
- *Impact:* `ExtractionOutput` is imported by `extraction.py` and tests — additive only at this step.

### A4 — Telos-aware extraction prompt
- New `app/intelligence/prompts/extract_semantic_objects.py`: `build_user_prompt(segment_text, metadata, pack, source_type)` injects telos summary, applicable semantic-object families + object types, salience preserve/ignore/downgrade rules, facet keys, required fields, and the output JSON shape. Add a matching `build_correction_prompt`.
- Unit test the prompt builder (string contains telos + families; deterministic given fixed pack).

### A5 — Projection layer
- New `app/intelligence/projection.py`:
  - `validate_object(obj) -> bool` — enforces ≥1 `source_refs` (evidence path) and salience ≥ pack threshold; drops otherwise.
  - `project(obj) -> ProjectedClaim` — `mvp_claim_type` → `claim_type`; `facets` split into `entities_json` (people/orgs/models/products/…) and `topics_json` (domain_terms + family/object_type + telos function); `epistemic.confidence` → `confidence`; stash the full v0.7 object dict under `entities_json["_v0_7"]` (forward-compat for Phase B backfill).
  - Enforce per-source / per-segment budgets from the pack.
- Unit tests covering the spec's MVP-projection table (e.g. `benchmark_result`→`benchmark_result`, `funding_round`→`funding_event`, `deprecation`→`other`).

### A6 — Wire the extraction graph to the new path
- `gitnexus_impact` on `_extract_one_span`, `extract_spans`, `store_claims`, `make_extraction_graph`, `run_with_context` first; report blast radius (chat + routes_claims + tests are downstream).
- Load the pack from `Source.domain_pack` (via `Document`) once per run; thread it through state.
- `_extract_one_span` → call A4 prompt + A3 schema, returning semantic objects.
- New `validate_and_project` step (or fold into `store_claims`) runs A5: validate → budget-gate → project → existing `Claim`/`ClaimEvidence` writes. Status lifecycle unchanged.
- Remove the old claim-only prompt/schema once green.
- Update affected tests (extraction graph tests) to the new path.

### A7 — (Stretch, recommended to scaffold) T2 semantic judgment
- `app/intelligence/prompts/judge_semantic_object.py` + an optional graph step that, for objects flagged `needs_escalation` or ambiguous family/type, asks T2 for evidence sufficiency + escalation decision, gated by `budgets.max_t2_calls_per_source`.
- If time-boxed out, log a `TODO.md` item and ship A1–A6 + deterministic salience gate only. *(Recommended: scaffold the prompt + a feature-flagged step; full relation classification waits for Phase B where relations have a home table.)*

### A8 — Evaluation compatibility
- Keep `evals/gold/claim_extraction/ai_tech_v2.yaml` as the compatibility fixture.
- Add a regression test asserting the new pipeline still produces valid projected claims for a known fixture document (object-schema-validity + projection-accuracy smoke).
- Add `mvp_claim_type_projection_accuracy` as a derived metric note in the eval docs (full object-level gold deferred to Phase B).

### A9 — Docs (Pre-PR, Step 6)
- `doc-updater` over: `docs/architecture.md` (extraction now telos-aware; pack is loaded; projection bridge; tier table), `docs/specs/domain-packs.md` (v3 purpose grammar + link to scheme spec), `docs/patterns.md` (semantic-object + projection pattern).

### Pre-PR gates (Step 6) and justification
- **`/simplify`** — required.
- **`doc-updater`** — required (A9).
- **`security-review`** — **justified**: A4/A6 inject domain-pack-controlled text and source content into LLM prompts, expanding the prompt-injection surface (untrusted source text + pack YAML). Review the prompt-assembly and projection paths.
- **`test-plan-writer`** — **justified**: the extraction hot path changes shape (new schema, projection, budget gates); a written test plan de-risks the cutover.

---

## 4. Phase B — outline (follow-up session, not this Step 4)

1. **Migration 0005** — `semantic_capsules`, `capsule_segments`, `semantic_relations`, `domain_packs`, `theses`, `decision_artefacts` (v0.7 §7.1).
2. **ORM models** + **dual-write**: projection writes a capsule (+ `capsule_segments`) alongside the projected claim; backfill capsules from the `_v0_7` blob stashed in Phase A.
3. **Capsule retrieval** + telos-aware hybrid scoring (pack `hybrid_score_weights`); query-intent classification.
4. **Relation classification** (T2/T3) writing `semantic_relations`.
5. **Lifecycle + consolidation** workers (capsule states; thesis/arc/research-model synthesis).
6. **Chat over capsules** + object-level eval gold sets; retire the claim-projection bridge.

---

## 5. Decisions taken (user offline → recommended path)

- **Bridge over big-bang migration** for this session — preserves API/chat/eval, lands value first.
- **Single domain (`personal_ai_tech`) first**, matching v0.7 Sprint 3 ("do not build all three at once").
- **Stash full v0.7 object in `entities_json._v0_7`** so Phase B can backfill capsules without re-extraction.
- **T2 judge scaffolded but feature-flagged** in Phase A; full relation/synthesis judgment in Phase B where relations have a table.
- **Plan written but uncommitted** — Step 5 (commit) deferred per the user's instruction.
