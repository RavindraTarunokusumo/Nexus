# Phase 3 Claim Extraction — Design

**Date:** 2026-05-17
**Status:** Approved
**Branch:** `feat/phase3-claim-extraction`

---

## Goal

Convert embedded document spans into atomic, evidence-grounded claims using a LangGraph-orchestrated LLM pipeline. Every claim links back to the span(s) that support it. This completes the evidence chain: `Source → Document → Span → Claim`.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| LLM workflow backbone | LangGraph `StateGraph` (pure — no LangChain agent stack) | Graph machinery for flow control; our own OpenRouter HTTP client for calls |
| Model tier | T2 (cheap structured extraction) | Extraction is T2 by MVP design; T3 is for synthesis (Phase 4+) |
| Retry strategy | Correction-prompt retry, max 2 per span | LangGraph conditional edges; zero extra cost on happy path |
| Span processing | Per-span concurrent, `asyncio.gather` + `Semaphore(5)` | Matches `Span → ClaimEvidence` schema; individual retry works cleanly |
| Execution model | Synchronous (blocks until complete) | Explicit operator action; full result in response; can be moved to worker in Phase 4+ |

---

## Architecture & Components

### New files

```
app/intelligence/
├── llm_client.py           — OpenRouter HTTP client with AgentRun logging
├── prompts/
│   └── extract_claims.py   — system + user prompt builders
└── extraction.py           — LangGraph StateGraph definition

app/api/
└── routes_claims.py        — POST /documents/{id}/extract-claims, GET /claims
```

### Modified files

- `app/main.py` — register claims router
- `app/config.py` — expose `openrouter_api_key`, `openrouter_t2_model` from Settings

### LangGraph graph (`extraction.py`)

**State:**

```python
class ExtractionState(TypedDict):
    document_id: uuid.UUID
    model: str                         # resolved from settings.openrouter_t2_model
    spans: list[dict]                  # loaded from DB
    results: list[dict]                # per-span: {span_id, claims, error, tokens}
    total_tokens: int
    error: str | None                  # fatal error string if graph aborts
```

**Nodes:**

| Node | Responsibility |
|---|---|
| `load_spans` | Fetch `Document` + all `Span` rows from DB; abort if document not in `embedded` status |
| `extract_spans` | `asyncio.gather` over per-span extraction; `Semaphore(5)` caps concurrency; each span call includes retry loop |
| `store_claims` | INSERT `claims` + `claim_evidence` rows; write per-call and summary `AgentRun` rows |
| `update_status` | Set `document.status` based on outcome |

**Edges:**

```
load_spans → extract_spans
extract_spans → store_claims    (if len(results with claims) > 0)
extract_spans → update_status   (via conditional edge — always reaches end)
store_claims → update_status
update_status → END
```

### LLMClient (`llm_client.py`)

```python
class LLMClient:
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        ...

    async def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> dict:
        """Call OpenRouter, validate response against schema, log AgentRun. Raises LLMError on failure."""
```

Writes one `AgentRun` row per call: `run_type`, `model`, `input_json`, `output_json`, `cost_estimate`, `status`.

---

## Data Flow

```
POST /documents/{doc_id}/extract-claims[?force=true]
  │
  ├── Validate: document exists, status == "embedded"   → 422 if not
  ├── Check: no existing claims                          → 409 if present (unless ?force=true)
  │     └── force=true: DELETE existing claims (CASCADE handles claim_evidence)
  │                     reset document.status = "embedded"
  │
  └── Compile and run ExtractionGraph

        load_spans
          └── Fetch Document + Spans ordered by span_index

        extract_spans  (asyncio.gather, Semaphore(5))
          └── For each span:
                call LLMClient.complete_json(schema=CLAIM_SCHEMA)
                  → validate JSON schema
                  → [fail] append correction to prompt, retry (max 2)
                  → [fail after 2] record span as extraction_error
                log one AgentRun row per LLM call (including retries)

        store_claims
          └── For each extracted claim:
                INSERT claims (claim_text, claim_type, entities_json,
                               topics_json, confidence, status="active")
                INSERT claim_evidence (claim_id, span_id,
                                       evidence_role="support", confidence)
              UPDATE document.status = "claims_extracted" | "extraction_partial"
              INSERT summary AgentRun (aggregate tokens + cost)

        update_status
          └── All spans failed → document.status = "extraction_failed"

  Response 200:
  {
    "document_id": "uuid",
    "claims_extracted": 12,
    "spans_processed": 8,
    "spans_failed": 0,
    "tokens_used": 4821,
    "cost_estimate_usd": 0.0007,
    "claim_ids": ["uuid", ...]
  }
```

---

## Extraction Prompt

**System prompt** (from `prompts/extract_claims.py`):

```
You are a precise claim extractor. Extract only atomic propositions
directly supported by the provided text.

Rules:
- Each claim expresses exactly one proposition.
- Each claim must stand alone without outside context.
- Map every claim to the span that supports it.
- Do not infer, speculate, or use outside knowledge.
- Prefer fewer high-quality claims over many low-confidence ones.
- Output valid JSON matching the provided schema exactly.
```

**User prompt:** the span text verbatim, plus the span's `metadata_json` (title, source, published date).

**Correction prompt** (on retry): appends the invalid response and the validation error before repeating the instruction.

---

## Claim Schema (JSON Schema, enforced by LLMClient)

```json
{
  "type": "object",
  "required": ["claims"],
  "properties": {
    "claims": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["claim_text", "claim_type", "entities", "topics", "confidence", "rationale"],
        "properties": {
          "claim_text":  { "type": "string" },
          "claim_type":  { "type": "string",
                           "enum": ["model_release", "benchmark_result", "product_launch",
                                    "pricing_change", "research_finding", "infrastructure_update",
                                    "security_issue", "funding_event", "regulation",
                                    "forecast", "other"] },
          "entities":    { "type": "array", "items": { "type": "string" } },
          "topics":      { "type": "array", "items": { "type": "string" } },
          "confidence":  { "type": "number", "minimum": 0, "maximum": 1 },
          "rationale":   { "type": "string" }
        }
      }
    }
  }
}
```

---

## API Contracts

### `POST /documents/{document_id}/extract-claims`

| Status | Condition |
|---|---|
| 200 | Extraction complete (full or partial) |
| 404 | Document not found |
| 409 | Claims already exist — use `?force=true` |
| 422 | Document not yet embedded |
| 503 | OpenRouter unreachable |

### `GET /claims`

Query params: `document_id` (required), `claim_type`, `status` (`active`/`rejected`), `limit` (default 50), `offset` (default 0).

Response: array of claim objects — `id`, `document_id`, `claim_text`, `claim_type`, `entities_json`, `topics_json`, `confidence`, `status`, `created_at`.

---

## Error Handling

**Document status lifecycle:**

```
fetched → chunked → embedded → claims_extracted
                              → extraction_partial  (some spans failed)
                              → extraction_failed   (all spans failed)
```

**Per-span failure matrix:**

| Failure | Action |
|---|---|
| LLM returns malformed JSON | Retry with correction prompt (max 2) |
| Schema validation fails after 2 retries | Mark span `extraction_error`; continue others |
| OpenRouter 4xx | Mark span failed; log AgentRun; continue |
| OpenRouter 5xx / network error | Abort entire graph → `extraction_failed` |
| Claim has no supporting span | Reject claim before INSERT; log to AgentRun |

**`?force=true`:** Deletes all `claims` rows for the document (CASCADE deletes `claim_evidence`), resets `document.status = "embedded"`, runs fresh extraction.

---

## Testing

### `tests/test_llm_client.py` — unit, httpx mock

- `complete_json` returns parsed dict on valid 200 response
- Raises `LLMError` on 4xx from OpenRouter
- Raises on response that fails JSON schema validation
- One `AgentRun` row written per call with correct `run_type`, `model`, token counts

### `tests/test_extraction_graph.py` — integration, testcontainers + mocked LLMClient

- Happy path: 3 spans → claims extracted → `document.status = "claims_extracted"`
- Retry path: first span call returns invalid JSON; second returns valid → claims stored
- All-fail path: all spans exhaust retries → `document.status = "extraction_failed"`
- `?force=true`: existing claims deleted before re-extraction

### `tests/test_routes_claims.py` — integration, testcontainers + mocked LLMClient

- `POST /extract-claims` on embedded document → 200 with summary
- `POST /extract-claims` on non-embedded document → 422
- `POST /extract-claims` twice without `?force` → 409
- `GET /claims?document_id=...` → correct claims returned
- `GET /claims?claim_type=model_release` → filtered correctly

---

## Acceptance Criteria

Phase 3 is complete when:

1. `POST /documents/{id}/extract-claims` runs the LangGraph graph and returns a claim summary
2. Claims are stored with correct `claim_type` and linked to their source spans via `claim_evidence`
3. `GET /claims?document_id=...` returns the extracted claims
4. `AgentRun` rows are written for every LLM call with model, tokens, and cost estimate
5. Retry-with-correction fires on schema failures; document reaches `extraction_failed` when all retries are exhausted
6. All new tests pass; existing 69-test suite shows no regressions

---

## Open Items (Phase 4+ scope)

- Brief synthesis using T3 model — consumes claims, generates `Brief` + `BriefItem` rows
- Query answering — retrieve claims + spans, synthesise grounded answer
- Move extraction to background worker (Celery/RQ) if latency becomes an issue
- `nexus document <id>` CLI command to show extracted claims inline
- Claim review/rejection UI or CLI flag
