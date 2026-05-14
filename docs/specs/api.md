# API Spec

## API Style

The MVP exposes a private REST API through FastAPI. Authentication can be basic for the private VPS deployment, but the API should still validate inputs and avoid leaking secrets or raw model payloads.

## Sources

### `POST /sources`

Creates a source definition.

Request:

```json
{
  "name": "string",
  "source_type": "rss",
  "url": "https://example.com/feed.xml",
  "domain_pack": "personal_ai_tech",
  "enabled": true,
  "credibility_score": 0.8
}
```

Behavior:

- validate supported `source_type`
- default `enabled` to true
- default `domain_pack` to `personal_ai_tech`
- reject duplicate source URLs unless explicitly allowed later

### `GET /sources`

Returns configured sources with ingestion status metadata.

## Ingestion

### `POST /ingest/rss/{source_id}`

Triggers ingestion for a configured RSS source.

Behavior:

- verify the source exists and has `source_type = rss`
- enqueue or run the ingestion pipeline
- return a run/job identifier

### `POST /ingest/url`

Ingests a manually supplied URL.

Request:

```json
{
  "url": "https://example.com/article",
  "domain_pack": "personal_ai_tech"
}
```

### `POST /ingest/text`

Ingests pasted text.

Request:

```json
{
  "title": "string",
  "text": "string",
  "source_name": "manual",
  "domain_pack": "personal_ai_tech"
}
```

## Documents

### `GET /documents`

Lists documents. Filters should include:

- source ID
- domain pack
- status
- date range

### `GET /documents/{document_id}`

Returns one document plus its spans and pipeline status summary.

## Claims

### `GET /claims`

Lists claims. Filters should include:

- document ID
- claim type
- topic
- entity
- status
- date range

### `POST /documents/{document_id}/extract-claims`

Triggers or retries claim extraction for a document.

Behavior:

- require the document to have clean text and spans
- log model calls in `agent_runs`
- reject or retry invalid schema outputs
- create evidence links for accepted claims

## Briefs

### `POST /briefs/generate`

Generates a brief.

Request:

```json
{
  "brief_type": "daily",
  "domain_pack": "personal_ai_tech",
  "date_range": {
    "start": "2026-05-01T00:00:00Z",
    "end": "2026-05-02T00:00:00Z"
  }
}
```

Behavior:

- retrieve relevant claims before synthesis
- validate structured brief output
- store brief and brief items
- link brief items to claims

### `GET /briefs`

Lists generated briefs.

### `GET /briefs/{brief_id}`

Returns one brief with items and linked claim IDs.

## Query

### `POST /query`

Answers a grounded question from retrieved evidence.

Request:

```json
{
  "question": "What changed this week in open-source LLMs?",
  "domain_pack": "personal_ai_tech",
  "top_k": 10
}
```

Response:

```json
{
  "answer": "string",
  "confidence": 0.0,
  "claim_ids": ["uuid"],
  "span_ids": ["uuid"],
  "source_links": ["string"],
  "uncertainty": "string"
}
```

Behavior:

- embed the query
- retrieve spans and claims
- synthesize only from retrieved evidence
- acknowledge missing or weak evidence
- return source links
- log query execution and model cost

## Error Handling

API errors should return structured JSON:

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {}
  }
}
```

Required error classes:

- validation error
- not found
- duplicate source/document
- unsupported source type
- pipeline unavailable
- extraction schema failure
- model gateway failure
