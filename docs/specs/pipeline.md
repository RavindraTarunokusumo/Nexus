# Pipeline Spec

## Pipeline Goal

The pipeline turns external source material into retrievable, evidence-grounded knowledge.

```text
fetch source
-> clean text
-> deduplicate
-> chunk into spans
-> generate embeddings
-> extract claims
-> store evidence links
-> update retrieval index
-> synthesize brief
```

## Supported Ingestion Types

| Type | MVP Support |
|---|---|
| RSS feed | Yes |
| Manual URL | Yes |
| Pasted text | Yes |
| API source | Deferred |
| PDF ingestion | Deferred |
| YouTube transcripts | Deferred |

## Ingestion Rules

The ingestion layer must:

- preserve source URL and source metadata
- store raw text before cleaning
- store clean text separately
- compute a content hash after normalization
- mark pipeline status on each document
- avoid duplicate processing when URL or content hash already exists

## Span Generation

Chunking must produce citeable spans with stable ordering.

Recommended defaults:

- chunk size: 400-800 tokens
- overlap: 50-100 tokens
- maximum chunk size: 1000 tokens

Each span should include metadata for:

- document title
- source name
- publication date
- chunk index
- token count
- domain pack

## Embeddings

Initial embedding model:

- `BAAI/bge-small-en-v1.5`

Alternative:

- `all-MiniLM-L6-v2`

Embeddings should run locally. Store span vectors in pgvector.

MVP retrieval targets:

- span semantic search
- claim semantic search

Deferred retrieval features:

- hybrid BM25 and vector fusion
- reranking models
- graph retrieval
- contradiction search

## Claim Extraction

> **Phase A Status: Telos-aware semantic-object extraction implemented** — `app/intelligence/extraction.py` (LangGraph `StateGraph`), `app/intelligence/prompts/extract_semantic_objects.py` (telos-aware prompt), `app/intelligence/projection.py` (validate → enforce_budgets → project), `app/intelligence/llm_client.py` (OpenRouter T2), `app/api/routes_claims.py`.

Claim extraction converts spans into atomic evidence-grounded propositions. As of Phase A, the production path produces `SemanticObject` instances that are projected to legacy `Claim` + `ClaimEvidence` rows via the domain pack's `mvp_claim_type` mapping.

Production structured output (`SemanticExtractionOutput`):

```json
{
  "objects": [
    {
      "core_type": "string",
      "claim_text": "string",
      "salience": 0.0,
      "facets": {},
      "epistemic_state": "string",
      "evidence_span_ids": ["string"]
    }
  ]
}
```

The full `SemanticObject` is preserved under `entities_json["_v0_7"]` in the `claims` table for forward-compat.

Extraction rules:

- extract only claims directly supported by the text
- map each claim to one or more evidence spans
- prefer fewer high-quality claims over many low-salience ones (floor: `SALIENCE_THRESHOLD = 0.3`)
- do not use outside knowledge
- do not summarize entire documents as claims
- respect per-source-type budgets defined in the domain pack

The legacy `ExtractionOutput` schema and `extract_claims.py` prompt remain in the codebase for `app/evaluation/runner.py` compatibility until Phase B.

## Retrieval

Query flow:

```text
user query
-> query embedding
-> retrieve spans and claims
-> rerank
-> build evidence context
-> grounded synthesis
```

Initial search features:

- semantic search
- top-k retrieval
- source filtering
- date filtering

The query system must answer only from retrieved evidence, acknowledge uncertainty, avoid fabricated claims, and include source links.

## Brief Synthesis

Brief types:

- `daily`
- `weekly`
- `query`

Brief structure:

1. Executive summary.
2. Major developments.
3. Research updates.
4. Tooling/products.
5. Watch-next items.

Synthesis rules:

- synthesize from claims
- cite supporting claims
- separate fact from interpretation
- preserve uncertainty
- avoid unsupported speculation

Structured output:

```json
{
  "title": "string",
  "executive_summary": "string",
  "items": [
    {
      "section": "string",
      "headline": "string",
      "what_happened": "string",
      "why_it_matters": "string",
      "claim_ids": ["string"],
      "confidence": 0.0,
      "watch_next": "string"
    }
  ]
}
```

## Worker Jobs

Required jobs:

- `fetch_source`
- `clean_document`
- `chunk_document`
- `embed_spans`
- `extract_claims`
- `generate_brief`
- `answer_query`

## Observability

The pipeline must log:

- ingestion failures
- extraction failures
- schema violations
- model calls
- token usage
- query execution
- worker errors

Initial metrics:

- documents ingested per day
- extraction success rate
- average claims per document
- query latency
- token usage per day
- brief generation time

## Future PoC Pipeline

The broader PoC adds:

- entity extraction
- claim relation classification
- signal extraction
- clustering and timelines
- thesis evaluation
- multimodal image triage
- knowledge lifecycle tiering
- T4 integrity audits
- query synthesis write-back

These are not required for Nexus Lite unless explicitly promoted into a later implementation plan.
