# Phase C — Reasoning Layer Design

**Date:** 2026-06-11
**Session:** compassionate-varahamihira-1d61fa
**Scope:** Three parallel workstreams: Phase B test-plan follow-ups, Phase 2 validation harness, Phase C C1+C2 reasoning layer.

---

## Workstream 1 — Phase B Test-Plan Follow-ups

### P1 — CLI smoke: `nexus capsules backfill --help`

**File:** `tests/test_cli_e2e.py` (append one function)

```python
def test_capsules_backfill_help_works():
    result = runner.invoke(app, ["capsules", "backfill", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.stdout
```

No DB fixture needed. Matches the existing `test_status_help_works()` pattern.

---

### P2a — Direct unit test for `build_capsule_row`

**File:** `tests/intelligence/test_capsules.py` (new)

Constructs a minimal `SemanticObject` with two `source_refs`, passes a fake 384-dim embedding, calls `build_capsule_row(...)`, asserts:

- `capsule.core_type == obj.core_type`
- `capsule.idempotency_key == build_capsule_idempotency_key(...)`
- `capsule.escalation_state == "flagged"` when `needs_escalation=True`, `"none"` otherwise
- `len(segments) == len(obj.source_refs)`
- Each `CapsuleSegment.role == "support"` (default fallback)
- Custom `evidence_roles` dict overrides role correctly
- `capsule.created_at` is set when passed, absent when omitted (DB default path)

No DB, no embedder; embedding passed in directly.

---

### P2b — Orphaned-span backfill skip path

**Bug:** In `app/intelligence/backfill.py::_write_batch`, the try/except wraps `capsule_from_claim` only. The `await session.commit()` call is **outside** the guard. A Claim whose `source_refs` reference a non-existent `Span` row produces a FK `IntegrityError` at commit time that bubbles uncaught, aborting the entire batch.

**Fix:** Wrap `session.commit()` in `_write_batch`:

```python
try:
    if dry_run:
        await session.rollback()
    else:
        await session.commit()
except Exception as exc:
    await session.rollback()
    result.errors.append(f"batch commit failed: {exc}")
    result.capsules_written -= len(rows_to_add_for_this_batch)
    # ... adjust segment count similarly
```

Because the entire batch is one `session.add_all`, a FK violation on any row rolls back all rows in that batch. The simplest correct fix is to catch the IntegrityError at commit, rollback, and log each row as an error — the batch counter adjustments ensure `BackfillResult` stays accurate.

**Test:** Append to `tests/intelligence/test_capsule_backfill.py`:

```python
async def test_backfill_skips_orphaned_span(session_factory):
    # seed Claim with _v0_7 blob referencing a non-existent span UUID
    # run backfill_capsules
    # assert result.errors is non-empty
    # assert result.capsules_written == 0
```

Requires the existing DB fixture (already present in that file).

---

## Workstream 2 — Phase 2 Validation Harness

**File:** `tests/test_validation_harness.py` (new)

Uses existing `session_factory` + `db_url` conftest fixtures. Adds a `truncate_all` async fixture that issues `DELETE FROM sources CASCADE` (or truncates in FK-safe order) to reset state between tests. This is the "destructive reset" described in the TODO.

Marked `@pytest.mark.slow` so fast-unit CI can skip.

### Tests

| Function | Path | Technique |
|---|---|---|
| `test_text_ingest_path` | `nexus ingest text` → document stored in DB | monkeypatches `http_ingest_text`; verifies CliRunner exit 0 |
| `test_rss_ingest_path` | `nexus ingest rss <source_id>` → count returned | monkeypatches `http_ingest_rss` |
| `test_status_path` | `nexus status --json` reflects seeded doc counts | CliRunner + DB seed (no monkeypatch needed) |
| `test_document_inspection_path` | `nexus document <id> --claims --json` returns title + claims | CliRunner + DB seed with Claim row |
| `test_semantic_search_path` | `nexus search "query" --json` → payload round-trip | monkeypatches `http_search_spans` |

Each test is independent via `truncate_all`. No server required.

---

## Workstream 3 — Phase C: C1 (T2 Judge Wiring) + C2 (Relation Classification)

### Graph shape after Phase C

```
load_spans
  → extract_spans
  → [error?] → update_status → END
  → validate_and_project
  → store_claims
  → judge_capsules        ← NEW C1
  → classify_relations    ← NEW C2
  → update_status → END
```

### ExtractionState additions

```python
stored_capsule_ids: list[uuid.UUID]   # parallel to stored_claim_ids; set by store_claims
judge_results: list[dict]             # [{capsule_id, verdict, relation_id}]; set by judge_capsules
relation_ids: list[uuid.UUID]         # SemanticRelation PKs; set by classify_relations
t2_calls_used: int                    # running budget counter initialised to 0
```

`store_claims` already iterates `(claim_id, capsule_id)` pairs; it returns `stored_capsule_ids` alongside `stored_claim_ids`.

---

### C1 — `judge_capsules` node

**Location:** `app/intelligence/extraction.py` (new nested async fn inside `make_extraction_graph`)

**Inputs from state:** `stored_capsule_ids`, `pack`, `model`, `t2_calls_used`

**Short-circuit:** `if state.get("error") or not state.get("stored_capsule_ids"): return {}`

**Logic:**

1. Load `SemanticCapsule` rows by `stored_capsule_ids` in one query.
2. Filter to `escalation_state == "flagged"` (set when `needs_escalation=True` at extraction time).
3. Cap at `pack.budgets.max_t2_calls_per_source - state["t2_calls_used"]`; skip remainder.
4. For each capsule:
   - Reconstruct a `SemanticObject` from capsule columns (text, core_type, domain_family/object_family, facets, epistemic_state).
   - Call `client.complete_json(model=t2_model, system=SYSTEM_PROMPT, user=build_judge_prompt(obj, pack), response_model=JudgeVerdict)`.
   - On success: write one `SemanticRelation` row:
     ```
     source_capsule_id = capsule.id
     target_capsule_id = None      # unary verdict, not a capsule-to-capsule relation
     target_thesis_id  = None
     relation_type     = "judge_escalated" | "judge_cleared"
     confidence        = verdict.recommended_confidence
     rationale         = verdict.rationale
     epistemic_state   = verdict.model_dump()
     created_by_tier   = "t2"
     created_by_model  = t2_model
     ```
   - Update `capsule.escalation_state` → `"escalated"` (if `verdict.escalate`) or `"reviewed"` (cleared).
   - Commit capsule update + relation row in one transaction.
5. Return `{"judge_results": [...], "t2_calls_used": t2_calls_used + n_judged}`.

**T2 model resolution:** `pack.model_routing_policy.models["T2"]["extractor"]` — falls back to `pack.model_routing_policy.default_route` lookup key `"semantic_compression_ambiguous"` if the structured key is absent. For `personal_ai_tech`: `deepseek/deepseek-v4-flash`.

---

### C2 — `classify_relations` node

**Location:** `app/intelligence/extraction.py` (new nested async fn)

**New file:** `app/intelligence/prompts/classify_relations.py`

**Short-circuit:** `if state.get("error") or len(state.get("stored_capsule_ids", [])) < 2: return {}`

**`classify_relations.py` contents:**

```python
class RelationClassification(BaseModel):
    relation_type: str      # must be in core_relations or domain_relations; "none" = no relation
    polarity: str | None    # "positive" | "negative" | None
    strength: float         # 0.0–1.0
    rationale: str

SYSTEM_PROMPT = "..."       # injected with core + domain relations from pack
def build_relation_prompt(cap_a, cap_b, pack) -> str: ...
```

**Node logic:**

1. Load full capsule rows for `stored_capsule_ids`.
2. Group by `object_family`. For each group, generate pairs `(A, B)` with `A.id < B.id` (canonical order, avoids duplicates).
3. Flatten all pairs; take the first `pack.budgets.max_relations_per_object` pairs across all families (budget cap).
4. For each pair:
   - Call LLM with `build_relation_prompt(cap_a, cap_b, pack)`, `response_model=RelationClassification`.
   - Skip if `relation_type == "none"` or empty.
   - Write `SemanticRelation`:
     ```
     source_capsule_id   = cap_a.id
     target_capsule_id   = cap_b.id
     relation_type       = classification.relation_type
     domain_relation_type = classification.relation_type if it's in pack.relation_grammar.domain_relations else None
     polarity            = classification.polarity
     strength            = classification.strength
     confidence          = classification.strength
     rationale           = classification.rationale
     created_by_tier     = "t2"
     created_by_model    = t2_model
     ```
5. Return `{"relation_ids": [<uuid>, ...]}`.

**Pair budget:** `max_relations_per_object` from `Budgets` (default 8). With e.g. 5 capsules of same family → 10 pairs → capped at 8. Cross-family pairs excluded in Phase C; Phase D can extend.

---

### New / modified files

| File | Change |
|---|---|
| `app/intelligence/extraction.py` | Add `judge_capsules` + `classify_relations` nodes; extend `ExtractionState`; wire edges |
| `app/intelligence/prompts/classify_relations.py` | New: `RelationClassification`, `SYSTEM_PROMPT`, `build_relation_prompt` |
| `tests/intelligence/test_judge_wiring.py` | New: unit tests for `judge_capsules` with mocked LLM |
| `tests/intelligence/test_relation_classification.py` | New: unit tests for `classify_relations` node + prompt builder |
| `tests/intelligence/test_capsules.py` | New: P2a unit tests for `build_capsule_row` |
| `tests/intelligence/test_capsule_backfill.py` | Append P2b orphaned-span test |
| `tests/test_cli_e2e.py` | Append P1 help smoke test |
| `tests/test_validation_harness.py` | New: Phase 2 harness (5 tests) |
| `app/intelligence/backfill.py` | P2b: wrap `session.commit()` in try/except |

---

## Testing matrix

| Test file | Marker | DB required |
|---|---|---|
| `test_cli_e2e.py` (P1 addition) | none | no |
| `tests/intelligence/test_capsules.py` | none | no |
| `tests/intelligence/test_capsule_backfill.py` (P2b addition) | asyncio | yes (Docker) |
| `tests/test_validation_harness.py` | slow, asyncio | yes (Docker) |
| `tests/intelligence/test_judge_wiring.py` | none | no (mock LLM) |
| `tests/intelligence/test_relation_classification.py` | none | no (mock LLM) |

---

## Constraints

- Phase C nodes must never raise: all LLM errors are caught and logged; the extraction succeeds even if judge/classify fail.
- `SemanticRelation` rows from judge verdicts have `target_capsule_id=None`; DB schema allows this (nullable).
- `classify_relations` only pairs capsules **within the current extraction batch** (same document). Cross-document relation discovery is Phase D.
- Relation classification uses the same T2 model as the judge. The T2 call budget is shared: judge calls + classify calls combined must not exceed `max_t2_calls_per_source`.
