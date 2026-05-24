# Hybrid Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-turn hybrid chatbot that answers user questions from retrieved spans plus extracted claims, with citations.

**Architecture:** Add a LangGraph chat answer graph parallel to claim extraction. The graph retrieves embedded spans, joins linked active claims, calls the existing OpenRouter `LLMClient` with `settings.t2_model`, validates citation labels, and returns a grounded answer through FastAPI and the CLI.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, pgvector, LangGraph, Pydantic, Typer, Rich, pytest, pre-commit.

---

## File Structure

- Modify: `TODO.md` - add a workflow session and sub-items before runtime edits.
- Modify: `app/intelligence/llm_client.py` - add a backward-compatible `run_type` keyword to `LLMClient.complete_json`.
- Modify: `app/observability/run_context.py` - add a chat-safe run context that binds `run_id` without a document.
- Create: `app/intelligence/prompts/chat_answer.py` - chat answer system prompt and user prompt builder.
- Create: `app/intelligence/chat.py` - chat answer schemas, retrieval helpers, LangGraph factory, and `run_chat_with_context`.
- Create: `app/api/routes_chat.py` - `POST /chat/answer` route.
- Modify: `app/main.py` - include the chat router.
- Modify: `app/cli/http.py` - add `chat_answer` HTTP wrapper and timeout.
- Modify: `app/cli/render.py` - add answer/citation renderer.
- Modify: `app/cli/main.py` - add `nexus chat`.
- Modify: `tests/conftest.py` - include the chat router in test apps.
- Modify: `tests/test_llm_client.py` - cover default and explicit run types.
- Create: `tests/test_chat_graph.py` - graph-level retrieval, hybrid context, insufficient evidence, and network error tests.
- Create: `tests/test_chat_api.py` - API-level response and error tests.
- Modify: `tests/test_cli_render.py` - render chat answer tests.
- Modify: `tests/test_cli_e2e.py` - CLI command tests with monkeypatched HTTP call.
- Modify: `docs/commands.md` - document `nexus chat` and `POST /chat/answer`.
- Modify: `docs/architecture.md` - update runtime flow and API endpoint table.

---

### Task 1: Workflow Ledger And Impact Checks

**Files:**
- Modify: `TODO.md`

- [ ] **Step 1: Confirm status before editing**

Run:

```powershell
git status --short --branch
```

Expected: branch is `codex/chatbot-workflow-session`; unrelated `AGENTS.md`, `CLAUDE.md`, and `.claude/worktrees/phase3-cli-testscript` may remain dirty and must not be staged.

- [ ] **Step 2: Record implementation sub-items**

Append a new active session to `TODO.md` before runtime edits:

```markdown
## 2026-05-22 Hybrid Chatbot

- [ ] LLM client run type support
- [ ] Hybrid chat graph and prompt
- [ ] Chat API route
- [ ] CLI chat command
- [ ] Docs and validation
```

- [ ] **Step 3: Run impact checks before symbol edits**

Run these before modifying the listed symbols:

```powershell
npx gitnexus impact --repo "C:\Users\rvind\OneDrive\Desktop\Projects\Nexus" LLMClient --direction upstream --include-tests
npx gitnexus impact --repo "C:\Users\rvind\OneDrive\Desktop\Projects\Nexus" complete_json --direction upstream --include-tests
npx gitnexus impact --repo "C:\Users\rvind\OneDrive\Desktop\Projects\Nexus" search_spans --direction upstream --include-tests
```

Expected: report direct callers and tests. If any result is HIGH or CRITICAL, stop and warn the user before editing.

- [ ] **Step 4: Commit ledger update**

Run:

```powershell
. .venv\Scripts\Activate.ps1
pre-commit run --files TODO.md
git add TODO.md
git commit -m "chore: track hybrid chatbot work"
git notes add -m "Summary: Added active TODO session for hybrid chatbot implementation." -m "Scope: TODO.md only." -m "Tests: pre-commit run --files TODO.md." -m "Risk: Low; workflow ledger only." -m "Docs: None." HEAD
```

Expected: one commit containing only `TODO.md`.

---

### Task 2: LLM Client Run Type

**Files:**
- Modify: `app/intelligence/llm_client.py`
- Modify: `tests/test_llm_client.py`

- [ ] **Step 1: Write failing tests**

Add tests to `tests/test_llm_client.py`:

```python
@pytest.mark.asyncio
async def test_complete_json_defaults_to_claim_extraction_run_type(client, fake_session_factory):
    openrouter_response = {
        "choices": [{"message": {"content": '{"value": "hello"}'}}],
        "usage": {"total_tokens": 50},
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: openrouter_response
        mock_post.return_value = mock_resp

        await client.complete_json(model="m", system="s", user="u", response_model=_SimpleOutput)

    agent_run = fake_session_factory.return_value.add.call_args[0][0]
    assert agent_run.run_type == "claim_extraction"


@pytest.mark.asyncio
async def test_complete_json_accepts_chat_answer_run_type(client, fake_session_factory):
    openrouter_response = {
        "choices": [{"message": {"content": '{"value": "hello"}'}}],
        "usage": {"total_tokens": 50},
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: openrouter_response
        mock_post.return_value = mock_resp

        await client.complete_json(
            model="m",
            system="s",
            user="u",
            response_model=_SimpleOutput,
            run_type="chat_answer",
        )

    agent_run = fake_session_factory.return_value.add.call_args[0][0]
    assert agent_run.run_type == "chat_answer"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_llm_client.py -k "run_type" -v
```

Expected: `test_complete_json_accepts_chat_answer_run_type` fails because `run_type` is not accepted.

- [ ] **Step 3: Implement minimal change**

Change `LLMClient.complete_json` signature and tracer call:

```python
async def complete_json(
    self,
    *,
    model: str,
    system: str,
    user: str,
    response_model: type[T],
    temperature: float = 0.1,
    max_tokens: int = 2000,
    run_type: str = "claim_extraction",
) -> tuple[T, int]:
    ...
    await record_agent_run(
        self._session_factory,
        run_type=run_type,
        model=model,
        input_payload={"system": system, "user": user},
        raw_output=raw_output,
        total_tokens=total_tokens,
        status=call_status,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_llm_client.py -k "run_type or happy_path" -v
```

Expected: selected tests pass and existing claim extraction default remains unchanged.

- [ ] **Step 5: Commit**

Run:

```powershell
pre-commit run --files app/intelligence/llm_client.py tests/test_llm_client.py
git add app/intelligence/llm_client.py tests/test_llm_client.py
git commit -m "feat: support typed llm run records"
git notes add -m "Summary: Added configurable LLM run_type while preserving claim extraction default." -m "Scope: app/intelligence/llm_client.py and tests/test_llm_client.py." -m "Tests: python -m pytest tests/test_llm_client.py -k 'run_type or happy_path' -v; pre-commit run --files app/intelligence/llm_client.py tests/test_llm_client.py." -m "Risk: Low; backward-compatible keyword default." -m "Docs: None." HEAD
```

---

### Task 3: Hybrid Chat Graph And Prompt

**Files:**
- Modify: `app/observability/run_context.py`
- Create: `app/intelligence/prompts/chat_answer.py`
- Create: `app/intelligence/chat.py`
- Create: `tests/test_chat_graph.py`

- [ ] **Step 1: Write failing graph tests**

Create `tests/test_chat_graph.py` with tests that seed one source, document, span, claim, and evidence row:

```python
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Source, Span
from app.intelligence.chat import make_chat_graph, run_chat_with_context
from app.intelligence.llm_client import LLMNetworkError


class FixedEmbedder:
    def embed_one(self, text):
        return [1.0] + [0.0] * 383


class FakeChatClient:
    def __init__(self, response=None, error=None):
        self.response = response or {"answer": "Model X was released.", "citations": ["C1"]}
        self.error = error
        self.calls = []

    async def complete_json(self, *, model, system, user, response_model, **kwargs):
        self.calls.append({"model": model, "system": system, "user": user, "kwargs": kwargs})
        if self.error:
            raise self.error
        return response_model.model_validate(self.response), 123


async def _seed_hybrid_context(session_factory: async_sessionmaker):
    async with session_factory() as session:
        source = Source(name="Feed", source_type="rss", url="https://feed.example/rss")
        session.add(source)
        await session.flush()
        doc = Document(
            source_id=source.id,
            title="Release article",
            url="https://example.com/release",
            raw_text="Model X was released.",
            clean_text="Model X was released.",
            content_hash=f"h-{uuid.uuid4()}",
            status="claims_extracted",
        )
        session.add(doc)
        await session.flush()
        span = Span(
            document_id=doc.id,
            span_index=0,
            text="Model X was released with open weights.",
            token_count=8,
            embedding=[1.0] + [0.0] * 383,
        )
        session.add(span)
        await session.flush()
        claim = Claim(
            document_id=doc.id,
            claim_text="Model X was released with open weights.",
            claim_type="model_release",
            entities_json=["Model X"],
            topics_json=["open weights"],
            confidence=0.9,
            status="active",
        )
        session.add(claim)
        await session.flush()
        session.add(
            ClaimEvidence(
                claim_id=claim.id,
                span_id=span.id,
                evidence_role="support",
                confidence=0.9,
            )
        )
        await session.commit()
        return doc.id, span.id, claim.id


@pytest.mark.asyncio
async def test_chat_graph_insufficient_evidence_skips_model(session_factory):
    client = FakeChatClient()
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "unknown question", "m", top_k=3)

    assert final["answer"].startswith("I do not have enough evidence")
    assert final["citations"] == []
    assert final["tokens_used"] == 0
    assert client.calls == []


@pytest.mark.asyncio
async def test_chat_graph_uses_spans_and_linked_claims(session_factory):
    _doc_id, span_id, claim_id = await _seed_hybrid_context(session_factory)
    client = FakeChatClient(response={"answer": "Model X was released.", "citations": ["C1"]})
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What was released?", "m", top_k=3)

    assert final["answer"] == "Model X was released."
    assert final["citations"][0]["span_id"] == span_id
    assert final["citations"][0]["claim_ids"] == [claim_id]
    assert "Model X was released with open weights." in client.calls[0]["user"]
    assert "run_type" in client.calls[0]["kwargs"]
    assert client.calls[0]["kwargs"]["run_type"] == "chat_answer"


@pytest.mark.asyncio
async def test_chat_graph_drops_unknown_citation_labels(session_factory):
    await _seed_hybrid_context(session_factory)
    client = FakeChatClient(response={"answer": "Answer.", "citations": ["C9"]})
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What happened?", "m", top_k=3)

    assert final["answer"] == "Answer."
    assert final["citations"] == []


@pytest.mark.asyncio
async def test_chat_graph_network_error_bubbles(session_factory):
    await _seed_hybrid_context(session_factory)
    client = FakeChatClient(error=LLMNetworkError("OpenRouter 503"))
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What happened?", "m", top_k=3)

    assert "OpenRouter 503" in final["error"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_chat_graph.py -v
```

Expected: import failure because `app.intelligence.chat` does not exist.

- [ ] **Step 3: Create prompt module**

Create `app/intelligence/prompts/chat_answer.py`:

```python
from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """You answer questions using only the provided Nexus context.
Return JSON with keys: answer, citations.
Use citation labels exactly as provided, such as C1.
If the context does not answer the question, say: I do not have enough evidence to answer that from the current corpus.
Do not use outside knowledge or speculation."""


def build_user_prompt(question: str, context_blocks: list[dict[str, Any]]) -> str:
    blocks = []
    for block in context_blocks:
        claims = "\n".join(f"- {claim['claim_text']}" for claim in block.get("claims", []))
        claims_text = claims if claims else "- No linked extracted claims."
        blocks.append(
            "\n".join(
                [
                    f"[{block['label']}]",
                    f"Title: {block.get('document_title') or '(untitled)'}",
                    f"URL: {block.get('url') or '(none)'}",
                    f"Span ID: {block['span_id']}",
                    f"Score: {block['score']:.3f}",
                    "Span text:",
                    block["text"],
                    "Linked claims:",
                    claims_text,
                ]
            )
        )
    return "\n\n".join(["Question:", question, "Context:", "\n\n".join(blocks)])
```

- [ ] **Step 4: Create chat graph**

Add a generic chat run context to `app/observability/run_context.py`:

```python
@asynccontextmanager
async def chat_run() -> AsyncIterator[uuid.UUID]:
    """Mint a run_id for chat answers without binding a document_id."""
    run_id = uuid.uuid4()
    t_run = run_id_var.set(run_id)
    try:
        yield run_id
    finally:
        run_id_var.reset(t_run)
```

Then create `app/intelligence/chat.py` with Pydantic schemas and graph factory:

```python
from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Span
from app.intelligence.llm_client import LLMNetworkError
from app.intelligence.prompts.chat_answer import SYSTEM_PROMPT, build_user_prompt
from app.observability.run_context import chat_run


class ChatAnswerOutput(BaseModel):
    answer: str
    citations: list[str]


class ChatCitation(BaseModel):
    document_id: uuid.UUID
    span_id: uuid.UUID
    document_title: str | None
    url: str | None
    score: float
    claim_ids: list[uuid.UUID]


class ChatState(TypedDict):
    question: str
    top_k: int
    model: str
    run_id: uuid.UUID | None
    context_blocks: list[dict[str, Any]]
    answer: str
    citation_labels: list[str]
    citations: list[dict[str, Any]]
    tokens_used: int
    error: str | None


INSUFFICIENT_EVIDENCE_ANSWER = (
    "I do not have enough evidence to answer that from the current corpus."
)
```

Implement `make_chat_graph(session_factory, client, embedder)` with nodes `retrieve_spans`, `load_claims`, `generate_answer`, and `format_result`. Use the same cosine-distance query as `routes_documents.search_spans`, join `Document`, assign labels `C1`, `C2`, and validate model citation labels against `context_blocks`.

- [ ] **Step 5: Add run helper**

Add to `app/intelligence/chat.py`:

```python
async def run_chat_with_context(graph, question: str, model: str, *, top_k: int) -> dict:
    async with chat_run() as run_id:
        final = await graph.ainvoke(
            {
                "question": question,
                "top_k": top_k,
                "model": model,
                "run_id": run_id,
                "context_blocks": [],
                "answer": "",
                "citation_labels": [],
                "citations": [],
                "tokens_used": 0,
                "error": None,
            }
        )
    final["run_id"] = run_id
    return final
```

- [ ] **Step 6: Run graph tests**

Run:

```powershell
python -m pytest tests/test_chat_graph.py -v
```

Expected: all chat graph tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
pre-commit run --files app/observability/run_context.py app/intelligence/prompts/chat_answer.py app/intelligence/chat.py tests/test_chat_graph.py
git add app/observability/run_context.py app/intelligence/prompts/chat_answer.py app/intelligence/chat.py tests/test_chat_graph.py
git commit -m "feat: add hybrid chat graph"
git notes add -m "Summary: Added LangGraph hybrid chat answer flow with prompt and tests." -m "Scope: app/observability/run_context.py, app/intelligence/chat.py, chat prompt, graph tests." -m "Tests: python -m pytest tests/test_chat_graph.py -v; pre-commit run --files app/observability/run_context.py app/intelligence/prompts/chat_answer.py app/intelligence/chat.py tests/test_chat_graph.py." -m "Risk: Medium; new retrieval and LLM answer path." -m "Docs: None." HEAD
```

---

### Task 4: Chat API Route

**Files:**
- Create: `app/api/routes_chat.py`
- Modify: `app/main.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_chat_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_chat_api.py`:

```python
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_answer_requires_embedder(client: AsyncClient):
    response = await client.post("/chat/answer", json={"question": "What changed?"})
    assert response.status_code == 503
    assert "Embedder" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_answer_returns_insufficient_evidence(client_with_embedder: AsyncClient):
    response = await client_with_embedder.post("/chat/answer", json={"question": "What changed?"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"].startswith("I do not have enough evidence")
    assert data["citations"] == []
    assert data["tokens_used"] == 0
    assert data["cost_estimate_usd"] == 0.0
    assert uuid.UUID(data["run_id"])
```

If testing a successful model response at route level requires monkeypatching the graph factory, add:

```python
@pytest.mark.asyncio
async def test_chat_answer_success_shape(monkeypatch, client_with_embedder: AsyncClient):
    async def fake_run_chat_with_context(graph, question, model, *, top_k):
        return {
            "answer": "Answer.",
            "citations": [],
            "run_id": uuid.uuid4(),
            "tokens_used": 10,
            "error": None,
        }

    monkeypatch.setattr("app.api.routes_chat.run_chat_with_context", fake_run_chat_with_context)
    response = await client_with_embedder.post("/chat/answer", json={"question": "What changed?"})
    assert response.status_code == 200
    assert response.json()["answer"] == "Answer."
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_chat_api.py -v
```

Expected: route not found or import failure.

- [ ] **Step 3: Implement route**

Create `app/api/routes_chat.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.intelligence.chat import ChatCitation, make_chat_graph, run_chat_with_context
from app.intelligence.llm_client import _COST_PER_TOKEN_USD, LLMClient

router = APIRouter(tags=["chat"])


class ChatAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2048)
    top_k: int = Field(default=8, ge=1, le=20)


class ChatAnswerResponse(BaseModel):
    answer: str
    citations: list[ChatCitation]
    retrieved_context_count: int
    run_id: uuid.UUID
    tokens_used: int
    cost_estimate_usd: float


@router.post("/chat/answer", response_model=ChatAnswerResponse)
async def answer_chat(payload: ChatAnswerRequest, request: Request) -> ChatAnswerResponse:
    from app.config import settings

    embedder = getattr(request.app.state, "embedder", None)
    if embedder is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedder not initialised.",
        )

    client = LLMClient(settings.openrouter_api_key, request.app.state.session_factory)
    graph = make_chat_graph(request.app.state.session_factory, client, embedder)
    final = await run_chat_with_context(
        graph,
        payload.question,
        settings.t2_model,
        top_k=payload.top_k,
    )
    if final.get("error"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chat answer failed: {final['error']}",
        )

    tokens = int(final.get("tokens_used") or 0)
    return ChatAnswerResponse(
        answer=final["answer"],
        citations=[ChatCitation.model_validate(c) for c in final.get("citations", [])],
        retrieved_context_count=len(final.get("context_blocks") or []),
        run_id=final["run_id"],
        tokens_used=tokens,
        cost_estimate_usd=round(tokens * _COST_PER_TOKEN_USD, 6),
    )
```

- [ ] **Step 4: Register router**

Modify `app/main.py`:

```python
from app.api.routes_chat import router as chat_router  # noqa: E402

app.include_router(chat_router)
```

Modify `tests/conftest.py` to import and include `chat_router` in `_build_app`.

- [ ] **Step 5: Run API tests**

Run:

```powershell
python -m pytest tests/test_chat_api.py tests/test_chat_graph.py -v
```

Expected: chat API and graph tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
pre-commit run --files app/api/routes_chat.py app/main.py tests/conftest.py tests/test_chat_api.py
git add app/api/routes_chat.py app/main.py tests/conftest.py tests/test_chat_api.py
git commit -m "feat: expose chat answer api"
git notes add -m "Summary: Added POST /chat/answer route for hybrid chatbot responses." -m "Scope: API route, app router registration, test app setup, API tests." -m "Tests: python -m pytest tests/test_chat_api.py tests/test_chat_graph.py -v; pre-commit run --files app/api/routes_chat.py app/main.py tests/conftest.py tests/test_chat_api.py." -m "Risk: Medium; new public API route." -m "Docs: Pending command and architecture docs task." HEAD
```

---

### Task 5: CLI Chat Command

**Files:**
- Modify: `app/cli/http.py`
- Modify: `app/cli/render.py`
- Modify: `app/cli/main.py`
- Modify: `tests/test_cli_render.py`
- Modify: `tests/test_cli_e2e.py`

- [ ] **Step 1: Write failing CLI tests**

Add to `tests/test_cli_render.py`:

```python
from app.cli.render import render_chat_answer


def test_render_chat_answer_human(capsys):
    render_chat_answer(
        {
            "answer": "Model X was released.",
            "citations": [
                {
                    "document_id": str(uuid.uuid4()),
                    "span_id": str(uuid.uuid4()),
                    "document_title": "Release article",
                    "url": "https://example.com/release",
                    "score": 0.91,
                    "claim_ids": [str(uuid.uuid4())],
                }
            ],
            "tokens_used": 123,
            "cost_estimate_usd": 0.000017,
        },
        json_output=False,
    )
    out = capsys.readouterr().out
    assert "Model X was released" in out
    assert "Release article" in out
    assert "0.91" in out
```

Add to `tests/test_cli_e2e.py`:

```python
@pytest.mark.asyncio
async def test_chat_command_calls_http(monkeypatch, db_url):
    captured = {}

    async def fake_chat(base_url, question, top_k):
        captured["base_url"] = base_url
        captured["question"] = question
        captured["top_k"] = top_k
        return {
            "answer": "Grounded answer.",
            "citations": [],
            "retrieved_context_count": 0,
            "run_id": str(uuid.uuid4()),
            "tokens_used": 0,
            "cost_estimate_usd": 0.0,
        }

    monkeypatch.setattr("app.cli.main.http_chat_answer", fake_chat)
    result = runner.invoke(
        app,
        ["chat", "What changed?", "--top-k", "5", "--json", "--api-url", "http://test.example"],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["question"] == "What changed?"
    assert captured["top_k"] == 5
    assert json.loads(result.stdout)["answer"] == "Grounded answer."
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli_render.py::test_render_chat_answer_human tests/test_cli_e2e.py::test_chat_command_calls_http -v
```

Expected: import or attribute failures because chat CLI/rendering is not implemented.

- [ ] **Step 3: Add HTTP wrapper**

Modify `app/cli/http.py`:

```python
_CHAT_TIMEOUT = httpx.Timeout(120.0)


async def chat_answer(base_url: str, question: str, top_k: int) -> dict:
    return await _request(
        "POST",
        base_url,
        "/chat/answer",
        json={"question": question, "top_k": top_k},
        timeout=_CHAT_TIMEOUT,
    )
```

- [ ] **Step 4: Add renderer**

Modify `app/cli/render.py`:

```python
def render_chat_answer(result: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        _print_json(result)
        return

    console.print(result.get("answer") or "")
    citations = result.get("citations") or []
    if not citations:
        console.print("[dim]No citations.[/dim]")
        return

    table = Table(title="Citations", show_header=True, header_style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Title")
    table.add_column("Span")
    table.add_column("URL")
    for c in citations:
        score = float(c.get("score") or 0.0)
        table.add_row(
            f"{score:.3f}",
            _short(c.get("document_title") or "", 40),
            _short(c.get("span_id") or "", 8),
            _short(c.get("url") or "", 60),
        )
    console.print(table)
```

- [ ] **Step 5: Add command**

Modify `app/cli/main.py` imports and add:

```python
from app.cli.http import chat_answer as http_chat_answer
from app.cli.render import render_chat_answer


@app.command()
def chat(
    question: str = typer.Argument(..., help="Natural language question to answer."),
    top_k: int = typer.Option(8, "--top-k", min=1, max=20),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Answer a question using embedded spans and extracted claims."""
    cfg = _settings(db_url, api_url)
    result = _run_http(http_chat_answer(cfg.api_base_url, question, top_k))
    render_chat_answer(result, json_output=json_output)
```

- [ ] **Step 6: Run CLI tests**

Run:

```powershell
python -m pytest tests/test_cli_render.py tests/test_cli_e2e.py -k "chat or search or extract" -v
```

Expected: selected CLI tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
pre-commit run --files app/cli/http.py app/cli/render.py app/cli/main.py tests/test_cli_render.py tests/test_cli_e2e.py
git add app/cli/http.py app/cli/render.py app/cli/main.py tests/test_cli_render.py tests/test_cli_e2e.py
git commit -m "feat: add chat cli command"
git notes add -m "Summary: Added nexus chat command and CLI rendering for answer citations." -m "Scope: CLI HTTP wrapper, renderer, command, CLI tests." -m "Tests: python -m pytest tests/test_cli_render.py tests/test_cli_e2e.py -k 'chat or search or extract' -v; pre-commit run --files app/cli/http.py app/cli/render.py app/cli/main.py tests/test_cli_render.py tests/test_cli_e2e.py." -m "Risk: Low; CLI command calls new API." -m "Docs: Command docs are handled in the docs validation task." HEAD
```

---

### Task 6: Docs, Detect Changes, And Validation

**Files:**
- Modify: `docs/commands.md`
- Modify: `docs/architecture.md`
- Modify: `TODO.md`

- [ ] **Step 1: Update docs**

In `docs/commands.md`, add a `nexus chat` section with this content:

```text
### `nexus chat`

Ask a single-turn question answered from embedded spans and extracted claims.

nexus chat "What changed in recent open-source LLM releases?"
nexus chat "What changed?" --top-k 5
nexus chat "What changed?" --json

The server must be running. The response includes a grounded answer and citations to retrieved spans.
```

In `docs/architecture.md`, add `POST /chat/answer` to the endpoint table and update runtime flow:

```text
claim extraction -> query answering (hybrid span + claim retrieval)
```

- [ ] **Step 2: Run documentation checks**

Run:

```powershell
pre-commit run --files docs/commands.md docs/architecture.md
```

Expected: docs checks pass.

- [ ] **Step 3: Run GitNexus detect changes before final commits**

Run:

```powershell
npx gitnexus detect-changes --repo "C:\Users\rvind\OneDrive\Desktop\Projects\Nexus"
```

Expected: changed symbols map to `LLMClient.complete_json`, chat graph, chat route, CLI chat command, render/chat HTTP helpers, and docs. If unrelated flows appear, inspect before committing.

- [ ] **Step 4: Run validation suite**

Run:

```powershell
python -m pytest tests/test_llm_client.py tests/test_chat_graph.py tests/test_chat_api.py tests/test_cli_render.py tests/test_cli_e2e.py -v
ruff check .
ruff format --check .
```

Expected: all selected tests, lint, and format checks pass.

- [ ] **Step 5: Commit docs and mark completed ledger items**

Update `TODO.md` completed sub-items with commit hashes from Tasks 2 through 5. Then run:

```powershell
pre-commit run --files docs/commands.md docs/architecture.md TODO.md
git add docs/commands.md docs/architecture.md TODO.md
git commit -m "docs: document hybrid chatbot"
git notes add -m "Summary: Documented chat API and CLI and tagged completed task ledger items." -m "Scope: docs/commands.md, docs/architecture.md, TODO.md." -m "Tests: pre-commit run --files docs/commands.md docs/architecture.md TODO.md; selected pytest and ruff validation from previous step." -m "Risk: Low; docs and workflow ledger only." -m "Docs: Updated command and architecture docs." HEAD
```

- [ ] **Step 6: Pre-PR skills and checks**

Run the required Workflow Step 6 checks:

```powershell
python -m pytest tests/test_llm_client.py tests/test_chat_graph.py tests/test_chat_api.py tests/test_cli_render.py tests/test_cli_e2e.py -v
pre-commit run --all-files
npx gitnexus detect-changes --repo "C:\Users\rvind\OneDrive\Desktop\Projects\Nexus"
```

Then invoke:

- `simplify` because runtime code changed.
- `test-plan-writer` because behavior/API/tests changed.
- `security-review` because the chatbot accepts user input and calls an external LLM gateway.

Expected: Step 6 is confirmed with validation results and any residual risks.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-hybrid-chatbot.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session with checkpoints for review.
