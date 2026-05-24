# Hybrid Chatbot Design

## Goal

Build the first Nexus chatbot surface so users can ask a single natural-language question and receive a grounded answer from the existing embedded spans and extracted claims.

## Scope

This design covers a single-turn chatbot API and matching CLI command. It does not add chat history, sessions, streaming, user accounts, answer persistence, or new database tables.

The chatbot must:

- Retrieve relevant embedded spans with the existing local embedder and pgvector search pattern.
- Enrich retrieved spans with active extracted claims linked through `claim_evidence`.
- Generate an answer with the same LangGraph setup and `settings.t2_model` model tier used by claim extraction.
- Return citations that preserve provenance back to span, document, and source URL where available.
- Record LLM usage in `agent_runs` with a chatbot-specific run type.

## Architecture

Add a focused chatbot graph in `app/intelligence/chat.py`. The graph should mirror the existing claim extraction pattern: a `StateGraph` factory bound to `session_factory`, a model client, and runtime dependencies supplied by the FastAPI route.

The graph should have four logical stages:

1. `retrieve_spans`: embed the user question with the existing `request.app.state.embedder`, query spans ordered by cosine distance, and carry document metadata needed for citations.
2. `load_claims`: find active claims connected to retrieved spans through `claim_evidence`, grouped by span and document.
3. `generate_answer`: call `LLMClient.complete_json` with a chatbot prompt and a structured Pydantic response schema.
4. `format_result`: return the answer, citations, retrieved context summary, token usage, and cost estimate.

The implementation should keep retrieval and prompt-building deterministic outside the model call. The model should receive compact context blocks that include span text, document title, URL, score, and linked claim texts.

## API

Add `POST /chat/answer`.

Request:

```json
{
  "question": "What changed in recent open-source LLM releases?",
  "top_k": 8
}
```

Validation:

- `question`: required, 1 to 2048 characters.
- `top_k`: optional, default 8, range 1 to 20 for the first version.

Response:

```json
{
  "answer": "Grounded answer text.",
  "citations": [
    {
      "document_id": "00000000-0000-0000-0000-000000000000",
      "span_id": "00000000-0000-0000-0000-000000000000",
      "document_title": "Document title",
      "url": "https://example.com/article",
      "score": 0.82,
      "claim_ids": ["00000000-0000-0000-0000-000000000000"]
    }
  ],
  "retrieved_context_count": 3,
  "run_id": "00000000-0000-0000-0000-000000000000",
  "tokens_used": 900,
  "cost_estimate_usd": 0.000126
}
```

If no embedded spans exist or retrieval returns no usable context, return `200` with an insufficient-evidence answer, empty citations, zero token usage, and no model call.

If OpenRouter is unavailable, return `503` from the route, matching the claim extraction route style.

## CLI

Add:

```sh
nexus chat "What did the latest ingested sources say about open-source LLMs?"
nexus chat "What changed?" --top-k 5
nexus chat "What changed?" --json
```

The CLI should call `POST /chat/answer`, print the answer first, and show citations as a compact table with score, title, span ID, and URL. JSON output should print the raw API response.

## LLM Client

`LLMClient.complete_json` currently records all calls as `run_type="claim_extraction"`. Add a backward-compatible `run_type` keyword argument defaulting to `"claim_extraction"` so existing claim extraction behavior remains unchanged and chatbot calls can record `"chat_answer"`.

The chatbot should use `settings.t2_model`, matching claim extraction as requested.

## Prompting

Add `app/intelligence/prompts/chat_answer.py`.

The system prompt should require the model to:

- Answer only from provided context.
- Say the evidence is insufficient when the context does not answer the question.
- Avoid unsupported facts and speculation.
- Return JSON matching the response schema.
- Include citation references for every substantive answer point.

The user prompt should include:

- The user question.
- Ordered context blocks with stable citation labels.
- For each block: document title, URL, span ID, score, span text, and linked extracted claims.

## Provenance

Every citation must include enough information for the caller to trace the answer back through:

```text
answer citation -> span -> document -> source
```

When linked claims are available, citations should also include `claim_ids`. The model may choose which retrieved context blocks support the answer, but the API must validate citation labels against retrieved context before returning them. Unknown citation labels should be dropped rather than exposing fabricated IDs.

## Testing

Add tests before implementation code:

- Chat graph returns an insufficient-evidence answer without calling the model when no embedded spans are available.
- Chat graph builds hybrid context that includes retrieved span text and linked active claims.
- API route returns answer, citations, run ID, token usage, and cost estimate for a successful fake model response.
- API route returns `503` when the model client raises `LLMNetworkError`.
- CLI `nexus chat` renders answer and citation rows.
- `LLMClient.complete_json` still defaults to `claim_extraction` and records `chat_answer` when requested.

## Risks And Constraints

- The first version is only as current as the ingested and embedded corpus.
- The answer may be incomplete when relevant documents have not reached claim extraction; using both spans and claims mitigates this.
- Citation validation is required because the model is allowed to reference only retrieved context labels.
- Chat history and persistent answer audit trails are intentionally deferred.
