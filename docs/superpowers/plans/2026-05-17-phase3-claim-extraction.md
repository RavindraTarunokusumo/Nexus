# Phase 3 Claim Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a LangGraph-orchestrated claim extraction pipeline that converts embedded document spans into atomic claims via OpenRouter (T2), storing results with full evidence links and AgentRun cost tracking.

**Architecture:** LangGraph `StateGraph` (4 nodes: load_spans → extract_spans → store_claims → update_status) orchestrates per-span concurrent LLM calls (Semaphore(5)) with correction-prompt retry (max 2). A standalone `LLMClient` handles OpenRouter HTTP, Pydantic schema validation, and per-call AgentRun logging. Two endpoints: `POST /documents/{id}/extract-claims` (synchronous) and `GET /claims`.

**Tech Stack:** Python 3.11+, langgraph>=0.2, httpx, Pydantic v2, SQLAlchemy async, FastAPI, pytest + testcontainers.

**Spec:** [docs/superpowers/specs/2026-05-17-phase3-claim-extraction-design.md](../specs/2026-05-17-phase3-claim-extraction-design.md)

---

## File Structure

**New files:**
- `app/intelligence/llm_client.py` — OpenRouter HTTP client, AgentRun logging, LLMError hierarchy
- `app/intelligence/prompts/__init__.py` — package marker
- `app/intelligence/prompts/extract_claims.py` — system prompt + user/correction prompt builders
- `app/api/routes_claims.py` — `POST /documents/{id}/extract-claims`, `GET /claims`
- `app/intelligence/extraction.py` — LangGraph graph factory + ExtractionState
- `tests/test_llm_client.py` — unit tests (httpx mock, no DB)
- `tests/test_extraction_graph.py` — integration tests (real DB, fake LLMClient)
- `tests/test_routes_claims.py` — integration tests (real DB, mocked graph)

**Modified files:**
- `pyproject.toml` — add `langgraph>=0.2.0`
- `app/main.py` — register `claims_router`
- `tests/conftest.py` — add `claims_router` to test client fixture

---

## Task 1: Add langgraph Dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add langgraph to dependencies**

In `pyproject.toml`, add `"langgraph>=0.2.0",` to the `dependencies` list after `tiktoken`:

```toml
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pgvector>=0.2.5",
    "pydantic-settings>=2.2.0",
    "feedparser>=6.0.11",
    "httpx>=0.27.0",
    "trafilatura>=1.9.0",
    "sentence-transformers>=3.0.0",
    "tiktoken>=0.7.0",
    "langgraph>=0.2.0",
    "typer>=0.12.0",
    "rich>=13.7.0",
]
```

- [ ] **Step 2: Install and verify**

Run: `python -m pip install -e ".[dev]"`
Then: `python -c "from langgraph.graph import StateGraph; print('langgraph ok')"`
Expected: `langgraph ok`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat(phase3): add langgraph dependency"
```

---

## Task 2: Extraction Prompts (TDD)

**Files:**
- Create: `app/intelligence/prompts/__init__.py`
- Create: `app/intelligence/prompts/extract_claims.py`
- Test: `tests/test_prompts.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_prompts.py`:

```python
"""Unit tests for extraction prompt builders."""
from app.intelligence.prompts.extract_claims import (
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)


def test_system_prompt_contains_rules():
    assert "atomic" in SYSTEM_PROMPT.lower() or "claim" in SYSTEM_PROMPT.lower()
    assert "json" in SYSTEM_PROMPT.lower()


def test_user_prompt_includes_span_text():
    prompt = build_user_prompt("GPT-5 released.", {"title": "AI News", "source_name": "Feed A"})
    assert "GPT-5 released." in prompt
    assert "AI News" in prompt
    assert "Feed A" in prompt


def test_user_prompt_handles_empty_metadata():
    prompt = build_user_prompt("Some text.", {})
    assert "Some text." in prompt


def test_correction_prompt_includes_error_and_original():
    original = "Extract from: hello world"
    invalid = '{"bad": true}'
    error = "field required: claim_text"
    prompt = build_correction_prompt(original, invalid, error)
    assert original in prompt
    assert invalid in prompt
    assert error in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.intelligence.prompts'`

- [ ] **Step 3: Create package marker and prompts module**

Create `app/intelligence/prompts/__init__.py`:

```python
"""Prompt builders for intelligence extraction tasks."""
```

Create `app/intelligence/prompts/extract_claims.py`:

```python
"""System and user prompt builders for claim extraction."""

SYSTEM_PROMPT = """\
You are a precise claim extractor for an intelligence research system.

Extract only atomic propositions directly supported by the provided text.

Rules:
- Each claim expresses exactly one proposition.
- Each claim must stand alone without outside context.
- Do not infer, speculate, or use outside knowledge.
- Prefer fewer high-quality claims over many low-confidence ones.
- Output valid JSON with a "claims" array matching the required schema exactly.
"""


def build_user_prompt(span_text: str, metadata: dict) -> str:
    """Build the initial extraction prompt for one span."""
    lines = ["Extract claims from the following text."]
    if metadata.get("title"):
        lines.append(f"Article title: {metadata['title']}")
    if metadata.get("source_name"):
        lines.append(f"Source: {metadata['source_name']}")
    if metadata.get("published_at"):
        lines.append(f"Published: {metadata['published_at']}")
    lines.append(f"\nText:\n{span_text}")
    return "\n".join(lines)


def build_correction_prompt(original_user: str, invalid_response: str, error: str) -> str:
    """Append correction instructions when the model returns invalid output."""
    return (
        f"{original_user}\n\n"
        f"---\n"
        f"Your previous response was invalid.\n"
        f"Error: {error}\n\n"
        f"Previous response:\n{invalid_response}\n\n"
        f"Please correct your response and return valid JSON matching the required schema exactly."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/intelligence/prompts/__init__.py app/intelligence/prompts/extract_claims.py tests/test_prompts.py
git commit -m "feat(phase3): add extraction prompt builders"
```

---

## Task 3: LLM Client (TDD)

**Files:**
- Create: `app/intelligence/llm_client.py`
- Create: `tests/test_llm_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_llm_client.py`:

```python
"""Unit tests for LLMClient — httpx mocked, no real OpenRouter calls."""
import uuid
from typing import Literal
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.intelligence.llm_client import (
    LLMClient,
    LLMNetworkError,
    LLMSchemaError,
)


class _SimpleOutput(BaseModel):
    value: str


@pytest.fixture
def fake_session_factory():
    """Session factory that accepts commits but writes nothing."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.add = AsyncMock()
    session.commit = AsyncMock()

    factory = AsyncMock()
    factory.return_value = session
    return factory


@pytest.fixture
def client(fake_session_factory):
    return LLMClient(api_key="test-key", session_factory=fake_session_factory)


@pytest.mark.asyncio
async def test_complete_json_happy_path(client):
    openrouter_response = {
        "choices": [{"message": {"content": '{"value": "hello"}'}}],
        "usage": {"total_tokens": 50},
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = openrouter_response
        mock_post.return_value = mock_resp

        result, tokens = await client.complete_json(
            model="openai/gpt-4o-mini",
            system="system",
            user="user",
            response_model=_SimpleOutput,
        )
    assert result.value == "hello"
    assert tokens == 50


@pytest.mark.asyncio
async def test_complete_json_5xx_raises_network_error(client):
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_post.return_value = mock_resp

        with pytest.raises(LLMNetworkError):
            await client.complete_json(
                model="openai/gpt-4o-mini",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )


@pytest.mark.asyncio
async def test_complete_json_4xx_raises_llm_error(client):
    from app.intelligence.llm_client import LLMError

    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_post.return_value = mock_resp

        with pytest.raises(LLMError):
            await client.complete_json(
                model="openai/gpt-4o-mini",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )


@pytest.mark.asyncio
async def test_complete_json_invalid_json_raises_schema_error(client):
    openrouter_response = {
        "choices": [{"message": {"content": "not-json"}}],
        "usage": {"total_tokens": 10},
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = openrouter_response
        mock_post.return_value = mock_resp

        with pytest.raises(LLMSchemaError):
            await client.complete_json(
                model="openai/gpt-4o-mini",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )


@pytest.mark.asyncio
async def test_complete_json_schema_mismatch_raises_schema_error(client):
    openrouter_response = {
        "choices": [{"message": {"content": '{"wrong_field": 123}'}}],
        "usage": {"total_tokens": 10},
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = openrouter_response
        mock_post.return_value = mock_resp

        with pytest.raises(LLMSchemaError):
            await client.complete_json(
                model="openai/gpt-4o-mini",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.intelligence.llm_client'`

- [ ] **Step 3: Implement llm_client.py**

Create `app/intelligence/llm_client.py`:

```python
"""OpenRouter HTTP client with per-call AgentRun logging."""
from __future__ import annotations

from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.db.models import AgentRun

_BASE_URL = "https://openrouter.ai/api/v1"
_TIMEOUT = httpx.Timeout(60.0)
# Approximate blended cost per token for gpt-4o-mini (clearly marked as estimate)
_COST_PER_TOKEN_USD = 0.30 / 1_000_000

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Non-retriable LLM error (4xx or unexpected response structure)."""


class LLMNetworkError(LLMError):
    """5xx or connection failure — callers should abort the pipeline."""


class LLMSchemaError(LLMError):
    """Response arrived but failed Pydantic validation — caller may retry with correction."""


class LLMClient:
    """Async OpenRouter client. Logs every call to AgentRun."""

    def __init__(self, api_key: str, session_factory: Any) -> None:
        self._api_key = api_key
        self._session_factory = session_factory

    async def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> tuple[T, int]:
        """Call OpenRouter and return (validated_result, total_tokens).

        Raises LLMNetworkError on 5xx / connection failure.
        Raises LLMError on 4xx.
        Raises LLMSchemaError if the response fails Pydantic validation.
        Always logs an AgentRun row (even on failure).
        """
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        raw_output: str | None = None
        total_tokens = 0
        call_status = "success"

        try:
            async with httpx.AsyncClient(
                base_url=_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=_TIMEOUT,
            ) as http:
                resp = await http.post("/chat/completions", json=payload)

            if resp.status_code >= 500:
                call_status = f"http_{resp.status_code}"
                raise LLMNetworkError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")

            if resp.status_code >= 400:
                call_status = f"http_{resp.status_code}"
                raise LLMError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            raw_output = data["choices"][0]["message"]["content"]
            total_tokens = data.get("usage", {}).get("total_tokens", 0)

        except (httpx.HTTPError, KeyError) as exc:
            call_status = "network_error"
            raise LLMNetworkError(str(exc)) from exc

        finally:
            await self._log(
                model=model,
                input_payload={"system": system[:300], "user": user[:300]},
                raw_output=raw_output,
                total_tokens=total_tokens,
                status=call_status,
            )

        try:
            validated = response_model.model_validate_json(raw_output)
        except (ValueError, ValidationError) as exc:
            raise LLMSchemaError(f"Schema validation failed: {exc}. Raw: {raw_output[:200]}") from exc

        return validated, total_tokens

    async def _log(
        self,
        *,
        model: str,
        input_payload: dict,
        raw_output: str | None,
        total_tokens: int,
        status: str,
    ) -> None:
        cost = total_tokens * _COST_PER_TOKEN_USD
        async with self._session_factory() as session:
            session.add(
                AgentRun(
                    run_type="claim_extraction",
                    model=model,
                    input_json=input_payload,
                    output_json={"raw": raw_output[:500] if raw_output else None},
                    cost_estimate=cost,
                    status=status,
                )
            )
            await session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/intelligence/llm_client.py tests/test_llm_client.py
git commit -m "feat(phase3): add LLMClient with OpenRouter HTTP and AgentRun logging"
```

---

## Task 4: LangGraph Extraction Graph (TDD)

**Files:**
- Create: `app/intelligence/extraction.py`
- Create: `tests/test_extraction_graph.py`

- [ ] **Step 1: Define the shared Pydantic extraction schema**

The extraction schema must be defined where both `llm_client.py` tests and `extraction.py` can import it. Add it to `app/intelligence/llm_client.py` at the bottom (after the class definition):

```python
# ---------------------------------------------------------------------------
# Extraction schema — imported by extraction.py and tests
# ---------------------------------------------------------------------------
from typing import Literal

ClaimType = Literal[
    "model_release",
    "benchmark_result",
    "product_launch",
    "pricing_change",
    "research_finding",
    "infrastructure_update",
    "security_issue",
    "funding_event",
    "regulation",
    "forecast",
    "other",
]


class ExtractedClaim(BaseModel):
    claim_text: str
    claim_type: ClaimType
    entities: list[str]
    topics: list[str]
    confidence: float
    rationale: str


class ExtractionOutput(BaseModel):
    claims: list[ExtractedClaim]
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_extraction_graph.py`:

```python
"""Integration tests for the LangGraph extraction graph.

Uses a real testcontainers DB but a fake LLMClient so no real OpenRouter calls are made.
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Source, Span
from app.intelligence.extraction import make_extraction_graph
from app.intelligence.llm_client import (
    ExtractionOutput,
    ExtractedClaim,
    LLMNetworkError,
    LLMSchemaError,
)


# ---------------------------------------------------------------------------
# Fake LLMClient
# ---------------------------------------------------------------------------


class FakeLLMClient:
    """Returns pre-configured results without making HTTP calls."""

    def __init__(self, responses: list):
        self._responses = iter(responses)
        self.calls: list[dict] = []

    async def complete_json(self, *, model, system, user, response_model, **kwargs):
        self.calls.append({"user": user})
        resp = next(self._responses)
        if isinstance(resp, BaseException):
            raise resp
        return response_model.model_validate(resp), 100

    async def _log(self, **_kwargs):
        pass


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_doc_with_spans(
    session_factory: async_sessionmaker,
    *,
    n_spans: int = 2,
    status: str = "embedded",
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    async with session_factory() as session:
        src = Source(name="S", source_type="rss", url=f"https://s{uuid.uuid4()}.example/feed")
        session.add(src)
        await session.flush()
        doc = Document(
            source_id=src.id,
            title="Doc",
            clean_text="x" * 100,
            content_hash=f"h-{uuid.uuid4()}",
            status=status,
        )
        session.add(doc)
        await session.flush()
        span_ids = []
        for i in range(n_spans):
            span = Span(
                document_id=doc.id,
                span_index=i,
                text=f"GPT-5 released with span {i}.",
                token_count=10,
                metadata_json={"title": "Doc", "source_name": "S"},
            )
            session.add(span)
            await session.flush()
            span_ids.append(span.id)
        await session.commit()
        return doc.id, span_ids


def _make_claim_response(claim_text: str = "GPT-5 was released."):
    return {
        "claims": [
            {
                "claim_text": claim_text,
                "claim_type": "model_release",
                "entities": ["OpenAI", "GPT-5"],
                "topics": ["LLM releases"],
                "confidence": 0.92,
                "rationale": "Directly stated in text.",
            }
        ]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_stores_claims(session_factory: async_sessionmaker, db_url: str):
    doc_id, span_ids = await _seed_doc_with_spans(session_factory, n_spans=2)
    client = FakeLLMClient(
        responses=[_make_claim_response("GPT-5 released."), _make_claim_response("GPT-5 fast.")]
    )
    graph = make_extraction_graph(session_factory, client)

    final = await graph.ainvoke({
        "document_id": doc_id,
        "model": "openai/gpt-4o-mini",
        "spans": [],
        "results": [],
        "total_tokens": 0,
        "error": None,
    })

    assert final.get("error") is None

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "claims_extracted"
        claims = (
            await session.execute(select(Claim).where(Claim.document_id == doc_id))
        ).scalars().all()
        assert len(claims) == 2
        evidences = (
            await session.execute(
                select(ClaimEvidence).where(ClaimEvidence.claim_id.in_([c.id for c in claims]))
            )
        ).scalars().all()
        assert len(evidences) == 2
        assert all(e.evidence_role == "support" for e in evidences)


@pytest.mark.asyncio
async def test_network_error_marks_document_failed(session_factory: async_sessionmaker):
    doc_id, _ = await _seed_doc_with_spans(session_factory, n_spans=1)
    client = FakeLLMClient(responses=[LLMNetworkError("OpenRouter 503")])
    graph = make_extraction_graph(session_factory, client)

    final = await graph.ainvoke({
        "document_id": doc_id,
        "model": "openai/gpt-4o-mini",
        "spans": [],
        "results": [],
        "total_tokens": 0,
        "error": None,
    })

    assert final.get("error") is not None
    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "extraction_failed"


@pytest.mark.asyncio
async def test_schema_error_retried_then_succeeds(session_factory: async_sessionmaker):
    """First call raises LLMSchemaError; second (correction) call succeeds."""
    doc_id, _ = await _seed_doc_with_spans(session_factory, n_spans=1)
    client = FakeLLMClient(
        responses=[LLMSchemaError("missing field"), _make_claim_response()]
    )
    graph = make_extraction_graph(session_factory, client)

    final = await graph.ainvoke({
        "document_id": doc_id,
        "model": "openai/gpt-4o-mini",
        "spans": [],
        "results": [],
        "total_tokens": 0,
        "error": None,
    })

    assert final.get("error") is None
    async with session_factory() as session:
        claims = (
            await session.execute(select(Claim).where(Claim.document_id == doc_id))
        ).scalars().all()
        assert len(claims) == 1
        assert len(client.calls) == 2  # first attempt + one retry


@pytest.mark.asyncio
async def test_all_retries_exhausted_sets_partial_status(session_factory: async_sessionmaker):
    """Two spans: first fails all retries, second succeeds → extraction_partial."""
    doc_id, _ = await _seed_doc_with_spans(session_factory, n_spans=2)
    # Span 0: fail 3 times (initial + 2 retries). Span 1: succeed immediately.
    client = FakeLLMClient(
        responses=[
            LLMSchemaError("e"),
            LLMSchemaError("e"),
            LLMSchemaError("e"),
            _make_claim_response(),
        ]
    )
    graph = make_extraction_graph(session_factory, client)

    await graph.ainvoke({
        "document_id": doc_id,
        "model": "openai/gpt-4o-mini",
        "spans": [],
        "results": [],
        "total_tokens": 0,
        "error": None,
    })

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "extraction_partial"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_extraction_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.intelligence.extraction'`

- [ ] **Step 4: Implement extraction.py**

Create `app/intelligence/extraction.py`:

```python
"""LangGraph extraction graph for per-span concurrent claim extraction."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Span
from app.intelligence.llm_client import (
    ExtractionOutput,
    LLMNetworkError,
    LLMSchemaError,
)
from app.intelligence.prompts.extract_claims import (
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)

_MAX_RETRIES = 2


class ExtractionState(TypedDict):
    document_id: uuid.UUID
    model: str
    spans: list[dict]
    results: list[dict]  # {span_id, claims, tokens, error}
    total_tokens: int
    error: str | None


async def _extract_one_span(span: dict, client: Any, model: str) -> dict:
    """Extract claims from one span with correction-prompt retry (max _MAX_RETRIES)."""
    user = build_user_prompt(span["text"], span.get("metadata_json") or {})
    total_tokens = 0

    for attempt in range(_MAX_RETRIES + 1):
        try:
            result, tokens = await client.complete_json(
                model=model,
                system=SYSTEM_PROMPT,
                user=user,
                response_model=ExtractionOutput,
            )
            total_tokens += tokens
            return {
                "span_id": span["id"],
                "claims": [c.model_dump() for c in result.claims],
                "tokens": total_tokens,
                "error": None,
            }
        except LLMNetworkError:
            raise  # abort the entire graph
        except LLMSchemaError as exc:
            if attempt < _MAX_RETRIES:
                # Append correction to the user turn and retry
                user = build_correction_prompt(user, "", str(exc))
                continue
            return {
                "span_id": span["id"],
                "claims": [],
                "tokens": total_tokens,
                "error": str(exc),
            }

    return {"span_id": span["id"], "claims": [], "tokens": 0, "error": "max retries exceeded"}


def make_extraction_graph(session_factory: async_sessionmaker, client: Any):
    """Build and compile the LangGraph extraction graph bound to session_factory and client."""

    async def load_spans(state: ExtractionState) -> dict:
        async with session_factory() as session:
            doc = await session.get(Document, state["document_id"])
            if doc is None:
                return {"error": f"Document {state['document_id']} not found"}
            if doc.status != "embedded":
                return {"error": f"Document status is '{doc.status}'; must be 'embedded'"}
            rows = (
                await session.execute(
                    select(Span)
                    .where(Span.document_id == state["document_id"])
                    .order_by(Span.span_index)
                )
            ).scalars().all()
            spans = [
                {
                    "id": str(s.id),
                    "text": s.text,
                    "token_count": s.token_count,
                    "metadata_json": s.metadata_json,
                }
                for s in rows
            ]
        return {"spans": spans}

    async def extract_spans(state: ExtractionState) -> dict:
        if state.get("error"):
            return {}

        semaphore = asyncio.Semaphore(5)

        async def bounded(span: dict) -> dict:
            async with semaphore:
                return await _extract_one_span(span, client, state["model"])

        try:
            results = list(await asyncio.gather(*[bounded(s) for s in state["spans"]]))
        except LLMNetworkError as exc:
            return {"error": str(exc), "results": []}

        total = sum(r.get("tokens", 0) for r in results)
        return {"results": results, "total_tokens": total}

    async def store_claims(state: ExtractionState) -> dict:
        async with session_factory() as session:
            for result in state.get("results", []):
                if result.get("error"):
                    continue
                for claim_data in result.get("claims", []):
                    claim = Claim(
                        document_id=state["document_id"],
                        claim_text=claim_data["claim_text"],
                        claim_type=claim_data["claim_type"],
                        entities_json=claim_data.get("entities"),
                        topics_json=claim_data.get("topics"),
                        confidence=claim_data.get("confidence"),
                        status="active",
                    )
                    session.add(claim)
                    await session.flush()
                    session.add(
                        ClaimEvidence(
                            claim_id=claim.id,
                            span_id=uuid.UUID(result["span_id"]),
                            evidence_role="support",
                            confidence=claim_data.get("confidence"),
                        )
                    )
            await session.commit()
        return {}

    async def update_status(state: ExtractionState) -> dict:
        if state.get("error"):
            new_status = "extraction_failed"
        else:
            results = state.get("results", [])
            if not results:
                new_status = "extraction_failed"
            else:
                failed = sum(1 for r in results if r.get("error"))
                if failed == 0:
                    new_status = "claims_extracted"
                elif failed < len(results):
                    new_status = "extraction_partial"
                else:
                    new_status = "extraction_failed"

        async with session_factory() as session:
            doc = await session.get(Document, state["document_id"])
            if doc:
                doc.status = new_status
                await session.commit()
        return {}

    def _route_after_extract(state: ExtractionState) -> str:
        return "update_status" if state.get("error") else "store_claims"

    builder = StateGraph(ExtractionState)
    builder.add_node("load_spans", load_spans)
    builder.add_node("extract_spans", extract_spans)
    builder.add_node("store_claims", store_claims)
    builder.add_node("update_status", update_status)

    builder.set_entry_point("load_spans")
    builder.add_edge("load_spans", "extract_spans")
    builder.add_conditional_edges(
        "extract_spans",
        _route_after_extract,
        {"store_claims": "store_claims", "update_status": "update_status"},
    )
    builder.add_edge("store_claims", "update_status")
    builder.add_edge("update_status", END)

    return builder.compile()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_extraction_graph.py -v`
Expected: 4 passed.

Note: the `test_all_retries_exhausted_sets_partial_status` test relies on the order that `asyncio.gather` processes spans matching the order responses are consumed. Because gather runs concurrently, the test seeds exactly 2 spans and provides exactly 3 schema errors (for span 0) followed by 1 success (for span 1). If the test is flaky due to ordering, add `n_spans=1` for the failure test and a separate test for the success span.

- [ ] **Step 6: Commit**

```bash
git add app/intelligence/llm_client.py app/intelligence/extraction.py tests/test_extraction_graph.py
git commit -m "feat(phase3): add LangGraph extraction graph with per-span retry"
```

---

## Task 5: Claims Routes + Wiring (TDD)

**Files:**
- Create: `app/api/routes_claims.py`
- Modify: `app/main.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_routes_claims.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_routes_claims.py`:

```python
"""Integration tests for claim extraction endpoints."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, Document, Source, Span


async def _seed_embedded_doc(session_factory: async_sessionmaker) -> tuple[uuid.UUID, uuid.UUID]:
    async with session_factory() as session:
        src = Source(name="Src", source_type="rss", url=f"https://s{uuid.uuid4()}.example/feed")
        session.add(src)
        await session.flush()
        doc = Document(
            source_id=src.id,
            title="Article",
            clean_text="x" * 200,
            content_hash=f"h-{uuid.uuid4()}",
            status="embedded",
        )
        session.add(doc)
        await session.flush()
        span = Span(
            document_id=doc.id,
            span_index=0,
            text="GPT-5 released.",
            token_count=5,
            metadata_json={"title": "Article"},
        )
        session.add(span)
        await session.commit()
        return doc.id, span.id


def _fake_graph_response(doc_id: uuid.UUID, span_id: uuid.UUID):
    """Pre-built final state that mimics a successful graph run."""
    return {
        "document_id": doc_id,
        "model": "openai/gpt-4o-mini",
        "spans": [{"id": str(span_id), "text": "GPT-5 released.", "token_count": 5, "metadata_json": {}}],
        "results": [
            {
                "span_id": str(span_id),
                "claims": [
                    {
                        "claim_text": "GPT-5 was released.",
                        "claim_type": "model_release",
                        "entities": ["OpenAI"],
                        "topics": ["LLM"],
                        "confidence": 0.9,
                        "rationale": "Directly stated.",
                    }
                ],
                "tokens": 100,
                "error": None,
            }
        ],
        "total_tokens": 100,
        "error": None,
    }


@pytest.mark.asyncio
async def test_extract_claims_success(
    client: AsyncClient, session_factory: async_sessionmaker, monkeypatch
):
    doc_id, span_id = await _seed_embedded_doc(session_factory)

    # Mock the graph: it returns a known final state but store_claims does NOT run.
    # We manually seed a claim to simulate what the graph would have stored.
    async with session_factory() as session:
        claim = Claim(
            document_id=doc_id,
            claim_text="GPT-5 was released.",
            claim_type="model_release",
            entities_json=["OpenAI"],
            topics_json=["LLM"],
            confidence=0.9,
            status="active",
        )
        session.add(claim)
        doc = await session.get(Document, doc_id)
        doc.status = "claims_extracted"
        await session.commit()

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=_fake_graph_response(doc_id, span_id))

    monkeypatch.setattr(
        "app.api.routes_claims.make_extraction_graph", lambda *_: mock_graph
    )

    resp = await client.post(f"/documents/{doc_id}/extract-claims")
    assert resp.status_code == 200
    data = resp.json()
    assert data["document_id"] == str(doc_id)
    assert data["total_tokens"] == 100
    assert isinstance(data["claim_ids"], list)


@pytest.mark.asyncio
async def test_extract_claims_404_for_unknown_doc(client: AsyncClient):
    resp = await client.post(f"/documents/{uuid.uuid4()}/extract-claims")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_extract_claims_422_when_not_embedded(
    client: AsyncClient, session_factory: async_sessionmaker
):
    async with session_factory() as session:
        src = Source(name="S", source_type="rss", url=f"https://x{uuid.uuid4()}.example")
        session.add(src)
        await session.flush()
        doc = Document(
            source_id=src.id, title="D", clean_text="y",
            content_hash=f"h-{uuid.uuid4()}", status="fetched"
        )
        session.add(doc)
        await session.commit()
        doc_id = doc.id

    resp = await client.post(f"/documents/{doc_id}/extract-claims")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_extract_claims_409_when_claims_already_exist(
    client: AsyncClient, session_factory: async_sessionmaker
):
    doc_id, _ = await _seed_embedded_doc(session_factory)
    async with session_factory() as session:
        session.add(Claim(
            document_id=doc_id, claim_text="existing", claim_type="other",
            entities_json=[], topics_json=[], confidence=0.5, status="active"
        ))
        await session.commit()

    resp = await client.post(f"/documents/{doc_id}/extract-claims")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_claims_returns_correct_claims(
    client: AsyncClient, session_factory: async_sessionmaker
):
    doc_id, _ = await _seed_embedded_doc(session_factory)
    async with session_factory() as session:
        for ct in ("model_release", "benchmark_result"):
            session.add(Claim(
                document_id=doc_id, claim_text=f"Claim {ct}", claim_type=ct,
                entities_json=[], topics_json=[], confidence=0.8, status="active"
            ))
        await session.commit()

    resp = await client.get(f"/claims?document_id={doc_id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_get_claims_filters_by_claim_type(
    client: AsyncClient, session_factory: async_sessionmaker
):
    doc_id, _ = await _seed_embedded_doc(session_factory)
    async with session_factory() as session:
        session.add(Claim(
            document_id=doc_id, claim_text="A", claim_type="model_release",
            entities_json=[], topics_json=[], confidence=0.9, status="active"
        ))
        session.add(Claim(
            document_id=doc_id, claim_text="B", claim_type="other",
            entities_json=[], topics_json=[], confidence=0.5, status="active"
        ))
        await session.commit()

    resp = await client.get(f"/claims?document_id={doc_id}&claim_type=model_release")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["claim_type"] == "model_release"


@pytest.mark.asyncio
async def test_get_claims_requires_document_id(client: AsyncClient):
    resp = await client.get("/claims")
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_routes_claims.py -v`
Expected: FAIL — router not registered yet.

- [ ] **Step 3: Create routes_claims.py**

Create `app/api/routes_claims.py`:

```python
"""Claim extraction endpoint and claims listing."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.api.deps import DbSession
from app.db.models import Claim, Document

router = APIRouter(tags=["claims"])

_COST_PER_TOKEN_USD = 0.30 / 1_000_000


class ClaimResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    claim_text: str
    claim_type: str
    entities_json: list | None
    topics_json: list | None
    confidence: float | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractionSummary(BaseModel):
    document_id: uuid.UUID
    claims_extracted: int
    spans_processed: int
    spans_failed: int
    tokens_used: int
    cost_estimate_usd: float
    claim_ids: list[uuid.UUID]


@router.post("/documents/{document_id}/extract-claims", response_model=ExtractionSummary)
async def extract_claims(
    document_id: uuid.UUID,
    request: Request,
    session: DbSession,
    force: bool = Query(default=False),
) -> ExtractionSummary:
    from app.config import settings
    from app.intelligence.extraction import make_extraction_graph
    from app.intelligence.llm_client import LLMClient

    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if doc.status not in ("embedded", "claims_extracted", "extraction_partial", "extraction_failed"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document status is '{doc.status}'; must be 'embedded' to extract claims.",
        )

    existing_claim_id = await session.scalar(
        select(Claim.id).where(Claim.document_id == document_id).limit(1)
    )
    if existing_claim_id is not None and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claims already exist. Use ?force=true to re-extract.",
        )

    if existing_claim_id is not None and force:
        await session.execute(delete(Claim).where(Claim.document_id == document_id))
        doc.status = "embedded"
        await session.commit()

    llm_client = LLMClient(
        api_key=settings.openrouter_api_key,
        session_factory=request.app.state.session_factory,
    )
    graph = make_extraction_graph(request.app.state.session_factory, llm_client)

    final = await graph.ainvoke({
        "document_id": document_id,
        "model": settings.openrouter_t2_model,
        "spans": [],
        "results": [],
        "total_tokens": 0,
        "error": None,
    })

    if final.get("error"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Extraction failed: {final['error']}",
        )

    results = final.get("results", [])
    spans_failed = sum(1 for r in results if r.get("error"))

    claim_ids = list(
        await session.scalars(select(Claim.id).where(Claim.document_id == document_id))
    )
    total_tokens = final.get("total_tokens", 0)

    return ExtractionSummary(
        document_id=document_id,
        claims_extracted=len(claim_ids),
        spans_processed=len(results),
        spans_failed=spans_failed,
        tokens_used=total_tokens,
        cost_estimate_usd=round(total_tokens * _COST_PER_TOKEN_USD, 6),
        claim_ids=claim_ids,
    )


@router.get("/claims", response_model=list[ClaimResponse])
async def list_claims(
    session: DbSession,
    document_id: uuid.UUID | None = None,
    claim_type: str | None = None,
    claim_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ClaimResponse]:
    if document_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_id query parameter is required.",
        )
    stmt = select(Claim).where(Claim.document_id == document_id)
    if claim_type is not None:
        stmt = stmt.where(Claim.claim_type == claim_type)
    if claim_status is not None:
        stmt = stmt.where(Claim.status == claim_status)
    stmt = stmt.order_by(Claim.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [ClaimResponse.model_validate(r) for r in rows]
```

- [ ] **Step 4: Register router in app/main.py**

Add after the existing router imports at the bottom of `app/main.py`:

```python
from app.api.routes_claims import router as claims_router  # noqa: E402

app.include_router(claims_router)
```

- [ ] **Step 5: Register router in tests/conftest.py**

Add `claims_router` import and include it in the test `client` fixture. Read `tests/conftest.py` first, then add:

```python
from app.api.routes_claims import router as claims_router
```

And inside the `client` fixture, after the existing `include_router` calls:

```python
test_app.include_router(claims_router)
```

- [ ] **Step 6: Run all claims tests**

Run: `python -m pytest tests/test_routes_claims.py -v`
Expected: 7 passed.

- [ ] **Step 7: Commit**

```bash
git add app/api/routes_claims.py app/main.py tests/conftest.py tests/test_routes_claims.py
git commit -m "feat(phase3): add claims extraction endpoint and GET /claims"
```

---

## Task 6: Final Verification

**Files:** None modified.

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -q --ignore=tests/test_embedder.py`
Expected: all tests pass (previous 69 + new ~16 = ~85 passing).

- [ ] **Step 2: Run pre-commit on all files**

Run: `python -m pre_commit run --all-files`
Expected: All hooks pass.

- [ ] **Step 3: Verify the nexus CLI still works**

Run: `nexus --help`
Expected: help lists all 8 commands (status, sources, documents, document, search, ingest ×3) — unchanged by Phase 3.

- [ ] **Step 4: Update TODO.md**

Add Phase 3 tasks to `TODO.md` under `## Active`:

```markdown
### Phase 3 — Claim Extraction (branch: feat/phase3-claim-extraction)

- [ ] T1: langgraph dependency (commit: ?)
- [ ] T2: Prompts module (commit: ?)
- [ ] T3: LLMClient with AgentRun logging (commit: ?)
- [ ] T4: LangGraph extraction graph (commit: ?)
- [ ] T5: Claims routes + wiring (commit: ?)
```

- [ ] **Step 5: Commit final state**

```bash
git add TODO.md
git commit -m "chore(phase3): update TODO with Phase 3 task tracking"
```

---

## Acceptance Verification

After Task 6, verify against the spec:

- [ ] **AC1: POST /extract-claims runs LangGraph graph and returns summary** — `test_extract_claims_success`
- [ ] **AC2: Claims stored with correct types linked to source spans** — `test_happy_path_stores_claims`
- [ ] **AC3: GET /claims returns extracted claims** — `test_get_claims_returns_correct_claims`
- [ ] **AC4: AgentRun rows written per LLM call** — `test_complete_json_happy_path` (fake_session_factory.add called)
- [ ] **AC5: Retry-with-correction fires on schema failures** — `test_schema_error_retried_then_succeeds`
- [ ] **AC6: All new tests pass, 69 existing tests unaffected** — Task 6 Step 1
