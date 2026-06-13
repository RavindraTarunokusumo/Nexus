# Phase D — Retrieval & UI Over Meaning: Design Spec

**Date:** 2026-06-12
**Branch:** to be created
**Status:** approved for implementation

---

## Goal

Cut over `/chat/answer` from span-based retrieval to semantic-capsule retrieval with telos-aware hybrid scoring and query-intent classification. Update the web UI citation cards to surface capsule metadata. Everything in one phase; table drop deferred to Phase E.

---

## Architecture

### Graph

Replace the current 4-node chat graph with a 4-node capsule graph:

```
classify_intent → retrieve_capsules → generate_answer → format_result
```

- `load_claims` is **eliminated** — capsule text is self-contained, no second DB pass needed.
- Conditional routing (skip to `format_result` on empty context) moves after `retrieve_capsules`.
- Framework: LangGraph `StateGraph` with `TypedDict` state — same pattern as today's `make_chat_graph`.

### Pre-requisite: Migration 0006

Add HNSW index on the existing `semantic_capsules.embedding VECTOR(384)` column (no schema change):

```sql
CREATE INDEX CONCURRENTLY ix_semantic_capsules_embedding_hnsw
ON semantic_capsules USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

---

## Data Model

### `ChatState` (TypedDict)

Add one field:

```python
query_intent: str   # e.g. "technical_deep_dive", "general"
```

All other fields unchanged (`context_blocks`, `answer`, `citation_labels`, `citations`, `tokens_used`, `error`).

### `context_blocks` dict shape

Replaces the span-based dict:

```python
{
    "label": "C1",
    "document_id": uuid.UUID,
    "capsule_id": uuid.UUID,
    "document_title": str | None,
    "url": str | None,
    "score": float,          # hybrid score
    "text": str,             # capsule.text
    "object_type": str,      # SemanticCapsule.domain_object_type
    "object_family": str,    # SemanticCapsule.object_family
    "lifecycle_state": str,  # SemanticCapsule.lifecycle_state
}
```

### `ChatCitation` (Pydantic, backend)

```python
class ChatCitation(BaseModel):
    document_id: uuid.UUID
    capsule_id: uuid.UUID        # replaces span_id
    document_title: str | None
    url: str | None
    score: float                 # hybrid score
    object_type: str | None      # domain_object_type
    object_family: str | None
    lifecycle_state: str | None
    summary: str                 # capsule.text, passed through to UI
    # claim_ids removed
```

### `ChatCitation` (TypeScript, frontend `client.ts`)

```typescript
export type ChatCitation = {
  document_id: string
  capsule_id: string           // replaces span_id
  document_title: string | null
  url: string | null
  score: number                // hybrid score
  object_type: string | null
  object_family: string | null
  lifecycle_state: string | null
  summary: string              // capsule text, shown in card
}
```

---

## Node Designs

### `classify_intent`

- Reads `state["question"]` and `state["pack"].retrieval_policy.query_intents` key names.
- Calls T2 LLM via `client.complete_json` with `IntentClassification` response model.
- Falls back to `"general"` if the returned intent name is not in the pack's intent keys.
- Writes `{"query_intent": intent_name}`.

Prompt module: `app/intelligence/prompts/classify_intent.py`

```python
class IntentClassification(BaseModel):
    intent: str

SYSTEM_PROMPT = """Classify the user's question into exactly one query intent.
Return JSON with key 'intent' containing the intent name.
If no intent fits, return 'general'."""

def build_classify_prompt(question: str, intent_names: list[str]) -> str:
    return f"Available intents: {', '.join(intent_names)}\n\nQuestion: {question}"
```

### `retrieve_capsules`

1. Sentinel check: if no capsule has an embedding, return `{"context_blocks": []}`.
2. Embed `state["question"]` with `embedder.embed_one`.
3. Run HNSW cosine query on `semantic_capsules.embedding`, joining `documents` for title/url. Fetch `top_k * 3` candidates (over-fetch to allow hybrid re-ranking).
4. Compute hybrid score for each candidate using weights from `pack.retrieval_policy.hybrid_score_weights`:

| Component | Weight | Computation |
|---|---|---|
| `semantic_similarity` | 0.35 | `1 - cosine_distance` (from HNSW result) |
| `domain_object_type_match` | 0.20 | 1.0 if `object_family` in intent `retrieval_priorities`; decayed by rank position; 0.5 if `retrieval_priorities` is empty |
| `source_authority` | 0.12 | constant 0.5 (no authority field yet; stubbed uniformly) |
| `recency` | 0.12 | min-max normalize `capsule.created_at` over candidate set |
| `salience` | 0.11 | `capsule.salience` directly (already in [0, 1]) |
| `relation_relevance` | 0.07 | **0.0 (stubbed)** |
| `evidence_quality` | 0.03 | **0.0 (stubbed)** |

5. Sort by hybrid score descending, keep top `top_k`.
6. Build `context_blocks` list. Writes `{"context_blocks": blocks}`.

The hybrid scorer is extracted as a pure module-level function `compute_hybrid_score(candidate, weights, intent_priorities, recency_range)` for testability.

### `generate_answer`

Unchanged except `build_user_prompt` format:

```
[C1]
Title: The Batch – Issue #247
URL: https://deeplearning.ai/...
Object type: model_release
Score: 0.912
Capsule:
GPT-5 released with 128k context and native tool-calling...
```

"Span ID:", "Span text:", and "Linked claims:" are removed. `SYSTEM_PROMPT` is unchanged.

### `format_result`

Builds `ChatCitation` from capsule context blocks. Removes `claim_ids`. Logic otherwise identical to today's `format_result`.

### Conditional routing

```python
def route_after_retrieve(state: ChatState) -> str:
    return "generate_answer" if state.get("context_blocks") else "format_result"
```

### `run_chat_with_context`

Updated initial state includes `query_intent: ""`.

---

## Prompts

### New: `app/intelligence/prompts/classify_intent.py`

See `classify_intent` node design above.

### Updated: `app/intelligence/prompts/chat_answer.py`

`build_user_prompt` updated to use capsule block format (object type + capsule text). `SYSTEM_PROMPT` unchanged.

---

## Web UI

### `web/src/api/client.ts`

Update `ChatCitation` type as shown in the data model section above.

### `web/src/components/CitationList.tsx`

Option A — enriched inline, minimal structural change:

- **Object-type badge**: blue pill (`bg-blue-100 text-blue-700`, uppercase, 10px) before the document title.
- **Lifecycle dot**: 8px circle, color-coded:
  - green (`bg-green-500`) for `active` / `confirmed`
  - amber (`bg-amber-400`) for `candidate`
  - gray (`bg-gray-400`) for all other states
- **Summary text**: replace the span-id / claim-count row with `citation.summary` truncated to ~120 chars; full text shown on expand.
- **Remove**: `claim_ids` count display.

No other frontend files change.

---

## Testing

### New files

| File | Tests | Notes |
|---|---|---|
| `tests/intelligence/test_chat_intent.py` | 4 | Pure unit: intent matched, fuzzy match canonicalized, fallback to `"general"`, pack with no query_intents |
| `tests/intelligence/test_chat_scoring.py` | 5 | Pure unit: weights applied correctly, recency normalization, object_family boost, stubbed weights are 0.0, scores sum to expected range |
| `tests/intelligence/test_chat_graph.py` | 6 | Pure unit (mock LLM + mock session): `classify_intent` writes query_intent, `retrieve_capsules` returns capsule blocks, sentinel skips retrieval, `format_result` builds new citation shape, insufficient evidence when no context, citation label normalization |

### Updated files

| File | Change |
|---|---|
| `tests/test_validation_harness.py` | Update slow semantic-search test: assert `capsule_id` present instead of `span_id` |

All new unit tests are pure (no DB, no live LLM) — mock `session_factory` and `client`.

---

## Out of Scope (Phase D)

- Drop `claims` / `claim_evidence` tables — deferred to Phase E (requires 1-week stability gate after cutover).
- `relation_relevance` and `evidence_quality` hybrid score components — stubbed at 0.0; implement when `SemanticRelation` query joins are profiled.
- `source_authority` field on `Document` / `Source` — stubbed at 0.5 uniformly.
- Thesis-level retrieval (`theses` table) — Phase E.
