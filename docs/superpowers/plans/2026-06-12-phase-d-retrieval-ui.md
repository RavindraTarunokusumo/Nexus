# Phase D — Retrieval & UI Over Meaning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut over `/chat/answer` from span-based to semantic-capsule HNSW retrieval with telos-aware hybrid scoring, LLM query-intent classification, and enriched citation cards in the web UI.

**Architecture:** Add a `classify_intent → retrieve_capsules → generate_answer → format_result` LangGraph graph in `app/intelligence/chat.py`, replacing the current `retrieve_spans → load_claims → generate_answer → format_result` chain. `load_claims` is eliminated — capsule text is self-contained. Hybrid scoring uses 5 active weights from the domain pack's `retrieval_policy.hybrid_score_weights`; `relation_relevance` and `evidence_quality` are stubbed at 0.0. The `pack` is loaded inside `run_chat_with_context` via `settings.default_pack_id` so no callers change.

**Tech Stack:** Python 3.12, LangGraph, SQLAlchemy async, pgvector (HNSW), Pydantic v2, pytest-asyncio, React + TypeScript, Vitest + Testing Library.

---

## File Structure

**Create:**
- `app/db/migrations/versions/0006_hnsw_capsule_index.py` — Alembic migration adding HNSW index
- `app/intelligence/prompts/classify_intent.py` — `IntentClassification` Pydantic model + `SYSTEM_PROMPT` + `build_classify_prompt`
- `tests/intelligence/test_chat_intent.py` — 4 pure unit tests for `_run_classify_intent`
- `tests/intelligence/test_chat_scoring.py` — 5 pure unit tests for `compute_hybrid_score`
- `tests/intelligence/test_chat_graph.py` — 6 pure unit tests for new graph nodes

**Modify:**
- `app/config.py` — add `default_pack_id: str = "personal_ai_tech"`
- `app/intelligence/chat.py` — full rewrite: new `ChatState`, new `ChatCitation`, `compute_hybrid_score`, `_run_classify_intent`, `_run_retrieve_capsules`, new graph
- `app/intelligence/prompts/chat_answer.py` — update `build_user_prompt` to capsule block format
- `web/src/api/client.ts` — update `ChatCitation` TypeScript type
- `web/src/components/CitationList.tsx` — object-type badge + lifecycle dot + summary text
- `web/src/test/components.test.tsx` — update `CITATION` fixture + `CitationList` assertions
- `tests/test_validation_harness.py` — update semantic-search slow test

---

## Task 1: Migration 0006 — HNSW index on `semantic_capsules.embedding`

**Files:**
- Create: `app/db/migrations/versions/0006_hnsw_capsule_index.py`

> No TDD for a pure DDL migration. Write the file, run `alembic upgrade head`, verify the index exists.

- [ ] **Step 1: Write the migration file**

```python
# app/db/migrations/versions/0006_hnsw_capsule_index.py
"""Add HNSW index on semantic_capsules.embedding for ANN retrieval.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_semantic_capsules_embedding_hnsw
        ON semantic_capsules
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_semantic_capsules_embedding_hnsw")
```

> **Note:** `CONCURRENTLY` is omitted — Alembic wraps migrations in transactions and `CREATE INDEX CONCURRENTLY` cannot run inside a transaction. This is safe for dev/CI; in production, run `CREATE INDEX CONCURRENTLY` manually before deploying.

- [ ] **Step 2: Run the migration**

```bash
cd <repo_root>
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
alembic upgrade head
```

Expected output ends with: `Running upgrade 0005 -> 0006`

- [ ] **Step 3: Verify index exists**

```bash
psql $DATABASE_URL -c "\d semantic_capsules" | grep hnsw
```

Expected: `ix_semantic_capsules_embedding_hnsw`

- [ ] **Step 4: Commit**

```bash
git add app/db/migrations/versions/0006_hnsw_capsule_index.py
git commit -m "feat(db): migration 0006 — HNSW index on semantic_capsules.embedding"
```

---

## Task 2: `classify_intent` prompt module + tests

**Files:**
- Create: `app/intelligence/prompts/classify_intent.py`
- Create: `tests/intelligence/test_chat_intent.py`

Note: `_run_classify_intent` will live in `app/intelligence/chat.py` (Task 4). The prompt module is a pure data file — write it first.

- [ ] **Step 1: Write the failing tests**

```python
# tests/intelligence/test_chat_intent.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.intelligence.llm_client import LLMNetworkError


def _make_pack(intent_keys: list[str]) -> MagicMock:
    pack = MagicMock()
    pack.retrieval_policy.query_intents = {k: {} for k in intent_keys}
    return pack


@pytest.mark.asyncio
async def test_classify_intent_matched() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.return_value = (MagicMock(intent="technical_deep_dive"), 50)
    pack = _make_pack(["technical_deep_dive", "landscape_scan"])
    state = {"question": "How does GPT-5 work?", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "technical_deep_dive"}


@pytest.mark.asyncio
async def test_classify_intent_unknown_falls_back_to_general() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.return_value = (MagicMock(intent="made_up_intent"), 50)
    pack = _make_pack(["technical_deep_dive"])
    state = {"question": "...", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general"}


@pytest.mark.asyncio
async def test_classify_intent_empty_pack_intents_skips_llm() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    pack = _make_pack([])
    state = {"question": "...", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general"}
    client.complete_json.assert_not_called()


@pytest.mark.asyncio
async def test_classify_intent_llm_error_falls_back_to_general() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.side_effect = LLMNetworkError("timeout")
    pack = _make_pack(["technical_deep_dive"])
    state = {"question": "...", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/Scripts/activate
pytest tests/intelligence/test_chat_intent.py -v
```

Expected: 4 ERRORS (ImportError — `_run_classify_intent` not yet defined in `chat.py`)

- [ ] **Step 3: Write `classify_intent.py` prompt module**

```python
# app/intelligence/prompts/classify_intent.py
from __future__ import annotations

from pydantic import BaseModel


class IntentClassification(BaseModel):
    intent: str


SYSTEM_PROMPT = (
    "Classify the user's question into exactly one query intent from the provided list. "
    "Return JSON with key 'intent' containing the intent name exactly as listed. "
    "If no intent fits, return 'general'."
)


def build_classify_prompt(question: str, intent_names: list[str]) -> str:
    joined = ", ".join(intent_names)
    return f"Available intents: {joined}\n\nQuestion: {question}"
```

- [ ] **Step 4: Add `_run_classify_intent` stub to `chat.py`**

Open `app/intelligence/chat.py` (current file: `app/intelligence/chat.py`). Add these imports at the top and the stub function before `make_chat_graph`. Do **not** change anything else yet — the full rewrite is Task 4.

Add to imports section:
```python
from app.intelligence.prompts.classify_intent import (
    SYSTEM_PROMPT as _INTENT_SYSTEM_PROMPT,
    IntentClassification,
    build_classify_prompt,
)
```

Add this module-level function before `make_chat_graph`:
```python
async def _run_classify_intent(state: dict, client: Any) -> dict:
    pack = state.get("pack")
    if pack is None:
        return {"query_intent": "general"}
    intent_names = list(pack.retrieval_policy.query_intents.keys())
    if not intent_names:
        return {"query_intent": "general"}
    try:
        result, _ = await client.complete_json(
            model=state["model"],
            system=_INTENT_SYSTEM_PROMPT,
            user=build_classify_prompt(state["question"], intent_names),
            response_model=IntentClassification,
            run_type="chat_classify_intent",
        )
        intent = result.intent if result.intent in intent_names else "general"
    except LLMNetworkError:
        intent = "general"
    return {"query_intent": intent}
```

- [ ] **Step 5: Run tests — all 4 should pass**

```bash
pytest tests/intelligence/test_chat_intent.py -v
```

Expected: 4 PASSED

- [ ] **Step 6: Run pre-commit**

```bash
pre-commit run --all-files
```

Expected: all hooks pass (SKIP=mypy,pytest-fast if needed).

- [ ] **Step 7: Commit**

```bash
git add app/intelligence/prompts/classify_intent.py app/intelligence/chat.py tests/intelligence/test_chat_intent.py
git commit -m "feat(chat): classify_intent prompt module and _run_classify_intent node helper"
```

---

## Task 3: Hybrid scoring helper + tests

**Files:**
- Modify: `app/intelligence/chat.py` (add `compute_hybrid_score`)
- Create: `tests/intelligence/test_chat_scoring.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/intelligence/test_chat_scoring.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest

_MIN = datetime(2025, 1, 1, tzinfo=timezone.utc)
_MAX = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _candidate(
    sem: float = 0.8,
    family: str = "technical_objects",
    salience: float = 0.7,
    created_at: datetime | None = None,
) -> dict:
    return {
        "semantic_sim": sem,
        "object_family": family,
        "salience": salience,
        "created_at": created_at or _MAX,
    }


def _weights(**kw: float) -> dict:
    base: dict[str, float] = {
        "semantic_similarity": 0.0,
        "domain_object_type_match": 0.0,
        "source_authority": 0.0,
        "recency": 0.0,
        "salience": 0.0,
        "relation_relevance": 0.0,
        "evidence_quality": 0.0,
    }
    base.update(kw)
    return base


def test_semantic_similarity_applied() -> None:
    from app.intelligence.chat import compute_hybrid_score

    score = compute_hybrid_score(
        _candidate(sem=0.9), _weights(semantic_similarity=1.0), [], _MIN, _MAX
    )
    assert abs(score - 0.9) < 1e-6


def test_object_family_boost_first_priority() -> None:
    from app.intelligence.chat import compute_hybrid_score

    score = compute_hybrid_score(
        _candidate(family="technical_objects"),
        _weights(domain_object_type_match=1.0),
        ["technical_objects", "market_objects"],
        _MIN,
        _MAX,
    )
    assert score == 1.0


def test_object_family_no_match_scores_zero() -> None:
    from app.intelligence.chat import compute_hybrid_score

    score = compute_hybrid_score(
        _candidate(family="other_family"),
        _weights(domain_object_type_match=1.0),
        ["technical_objects"],
        _MIN,
        _MAX,
    )
    assert score == 0.0


def test_stubbed_weights_contribute_zero() -> None:
    from app.intelligence.chat import compute_hybrid_score

    score = compute_hybrid_score(
        _candidate(sem=0.99, salience=0.99),
        _weights(relation_relevance=1.0, evidence_quality=1.0),
        [],
        _MIN,
        _MAX,
    )
    assert score == 0.0


def test_recency_newer_beats_older() -> None:
    from app.intelligence.chat import compute_hybrid_score

    w = _weights(recency=1.0)
    newer = compute_hybrid_score(_candidate(created_at=_MAX), w, [], _MIN, _MAX)
    older = compute_hybrid_score(_candidate(created_at=_MIN), w, [], _MIN, _MAX)
    assert newer > older
    assert 0.0 <= newer <= 1.0
    assert 0.0 <= older <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/intelligence/test_chat_scoring.py -v
```

Expected: 5 ERRORS (ImportError — `compute_hybrid_score` not yet defined)

- [ ] **Step 3: Add `compute_hybrid_score` to `app/intelligence/chat.py`**

Add this constant and function before `_run_classify_intent` in `chat.py`:

```python
# Priority score by rank in retrieval_priorities list
_PRIORITY_SCORES = [1.0, 0.5, 0.25, 0.1]


def compute_hybrid_score(
    candidate: dict,
    weights: dict[str, float],
    retrieval_priorities: list[str],
    recency_min: datetime,
    recency_max: datetime,
) -> float:
    """Compute telos-aware hybrid score. relation_relevance and evidence_quality are stubbed at 0."""
    # semantic_similarity
    sem = candidate["semantic_sim"] * weights.get("semantic_similarity", 0.0)

    # domain_object_type_match — boost by position in retrieval_priorities
    if not retrieval_priorities:
        dom_score = 0.5
    else:
        family = candidate["object_family"]
        try:
            rank = retrieval_priorities.index(family)
            dom_score = _PRIORITY_SCORES[rank] if rank < len(_PRIORITY_SCORES) else 0.1
        except ValueError:
            dom_score = 0.0
    dom = dom_score * weights.get("domain_object_type_match", 0.0)

    # source_authority — stubbed uniformly at 0.5 (no authority field yet)
    auth = 0.5 * weights.get("source_authority", 0.0)

    # recency — min-max normalize created_at over candidate set
    created_at = candidate["created_at"]
    if recency_min == recency_max:
        rec_score = 0.5
    else:
        span = (recency_max - recency_min).total_seconds()
        rec_score = (created_at - recency_min).total_seconds() / span
        rec_score = max(0.0, min(1.0, rec_score))
    rec = rec_score * weights.get("recency", 0.0)

    # salience — direct field
    sal = candidate["salience"] * weights.get("salience", 0.0)

    # relation_relevance (0.07) and evidence_quality (0.03) — stubbed at 0.0
    return sem + dom + auth + rec + sal
```

Also add this import at the top of `chat.py` (it's needed for `compute_hybrid_score`):
```python
from datetime import datetime, timezone
```

- [ ] **Step 4: Run tests — all 5 should pass**

```bash
pytest tests/intelligence/test_chat_scoring.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Run pre-commit and commit**

```bash
pre-commit run --all-files
git add app/intelligence/chat.py tests/intelligence/test_chat_scoring.py
git commit -m "feat(chat): compute_hybrid_score with 5 active weights (relation_relevance/evidence_quality stubbed)"
```

---

## Task 4: Chat graph rewrite (use Opus 4.8 model)

**Files:**
- Modify: `app/config.py`
- Modify: `app/intelligence/chat.py` (full rewrite of `ChatCitation`, `ChatState`, `make_chat_graph`, `run_chat_with_context`)
- Modify: `app/intelligence/prompts/chat_answer.py`
- Create: `tests/intelligence/test_chat_graph.py`

This task rewires the entire LangGraph chat pipeline. Read Phase D spec at `docs/superpowers/specs/2026-06-12-phase-d-retrieval-ui-design.md` before starting.

- [ ] **Step 1: Add `default_pack_id` to settings**

In `app/config.py`, add after `t3_model`:

```python
# Default domain pack loaded for /chat/answer and session turns.
default_pack_id: str = "personal_ai_tech"
```

Full updated file:
```python
# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required — no defaults so startup fails fast when not configured.
    database_url: str
    app_secret: str

    # Optional with sensible defaults.
    redis_url: str = "redis://localhost:6379/0"
    openrouter_api_key: str = ""

    # Model tiers — single place to swap all three:
    #   T1: local sentence-transformer (embedding, no API key needed)
    #   T2: fast LLM via OpenRouter (claim extraction)
    #   T3: strong LLM via OpenRouter (synthesis / query — future)
    t1_model: str = "BAAI/bge-small-en-v1.5"
    t2_model: str = "deepseek/deepseek-v4-flash"
    t3_model: str = "deepseek/deepseek-v4-pro"

    # Default domain pack loaded for /chat/answer and session turns.
    default_pack_id: str = "personal_ai_tech"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()  # type: ignore[call-arg]  # reads from env/.env at runtime
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/intelligence/test_chat_graph.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_session_factory(rows: list | None = None, has_sentinel: bool = True) -> MagicMock:
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.scalar = AsyncMock(return_value=MagicMock() if has_sentinel else None)

    exec_result = MagicMock()
    exec_result.all.return_value = rows or []
    mock_session.execute = AsyncMock(return_value=exec_result)

    sf = MagicMock()
    sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    sf.return_value.__aexit__ = AsyncMock(return_value=False)
    return sf


def _make_client(intent: str = "general", answer: str = "The answer", citations: list[str] | None = None) -> AsyncMock:
    client = AsyncMock()
    intent_result = MagicMock()
    intent_result.intent = intent
    answer_result = MagicMock()
    answer_result.answer = answer
    answer_result.citations = citations if citations is not None else ["C1"]
    client.complete_json = AsyncMock(
        side_effect=[(intent_result, 10), (answer_result, 100)]
    )
    return client


def _make_embedder() -> MagicMock:
    e = MagicMock()
    e.embed_one.return_value = [0.1] * 384
    return e


def _make_pack() -> MagicMock:
    pack = MagicMock()
    pack.retrieval_policy.query_intents = {}
    pack.retrieval_policy.hybrid_score_weights = {
        "semantic_similarity": 0.35,
        "domain_object_type_match": 0.20,
        "source_authority": 0.12,
        "recency": 0.12,
        "salience": 0.11,
        "relation_relevance": 0.07,
        "evidence_quality": 0.03,
    }
    return pack


def _capsule_row(capsule_id: uuid.UUID | None = None, doc_id: uuid.UUID | None = None) -> MagicMock:
    row = MagicMock()
    row.id = capsule_id or uuid.uuid4()
    row.document_id = doc_id or uuid.uuid4()
    row.text = "GPT-5 released with 128k context."
    row.domain_object_type = "model_release"
    row.object_family = "technical_objects"
    row.lifecycle_state = "active"
    row.salience = 0.8
    row.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.semantic_sim = 0.9
    row.title = "Release article"
    row.url = "https://example.com/release"
    return row


@pytest.mark.asyncio
async def test_classify_intent_writes_query_intent() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    result_mock = MagicMock()
    result_mock.intent = "technical_deep_dive"
    client.complete_json.return_value = (result_mock, 10)

    pack = MagicMock()
    pack.retrieval_policy.query_intents = {"technical_deep_dive": {}}
    state = {"question": "How does GPT-5 work?", "model": "test-model", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "technical_deep_dive"}


@pytest.mark.asyncio
async def test_retrieve_capsules_returns_labelled_blocks() -> None:
    from app.intelligence.chat import _run_retrieve_capsules

    capsule_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    sf = _make_session_factory(rows=[_capsule_row(capsule_id, doc_id)])
    embedder = _make_embedder()
    pack = _make_pack()

    state = {"question": "test", "top_k": 1, "query_intent": "general", "pack": pack}
    result = await _run_retrieve_capsules(state, sf, embedder)

    blocks = result["context_blocks"]
    assert len(blocks) == 1
    assert blocks[0]["label"] == "C1"
    assert blocks[0]["capsule_id"] == capsule_id
    assert blocks[0]["document_id"] == doc_id
    assert blocks[0]["text"] == "GPT-5 released with 128k context."
    assert blocks[0]["object_type"] == "model_release"


@pytest.mark.asyncio
async def test_retrieve_capsules_returns_empty_when_no_embeddings() -> None:
    from app.intelligence.chat import _run_retrieve_capsules

    sf = _make_session_factory(has_sentinel=False)
    embedder = _make_embedder()
    pack = _make_pack()

    state = {"question": "test", "top_k": 5, "query_intent": "general", "pack": pack}
    result = await _run_retrieve_capsules(state, sf, embedder)

    assert result == {"context_blocks": []}
    embedder.embed_one.assert_not_called()


@pytest.mark.asyncio
async def test_format_result_builds_capsule_citation() -> None:
    from app.intelligence.chat import make_chat_graph, run_chat_with_context

    capsule_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    sf = _make_session_factory(rows=[_capsule_row(capsule_id, doc_id)])
    client = _make_client(answer="GPT-5 is fast.", citations=["C1"])
    embedder = _make_embedder()
    pack = _make_pack()

    graph = make_chat_graph(sf, client, embedder)
    with patch("app.intelligence.chat.load_pack", return_value=pack):
        result = await run_chat_with_context(graph, "What is GPT-5?", "test-model", top_k=1)

    assert result["answer"] == "GPT-5 is fast."
    assert len(result["citations"]) == 1
    cit = result["citations"][0]
    assert str(cit["capsule_id"]) == str(capsule_id)
    assert cit["summary"] == "GPT-5 released with 128k context."
    assert "span_id" not in cit
    assert "claim_ids" not in cit


@pytest.mark.asyncio
async def test_insufficient_evidence_when_no_capsule_embeddings() -> None:
    from app.intelligence.chat import make_chat_graph, run_chat_with_context

    sf = _make_session_factory(has_sentinel=False)
    client = AsyncMock()
    embedder = _make_embedder()
    pack = _make_pack()

    graph = make_chat_graph(sf, client, embedder)
    with patch("app.intelligence.chat.load_pack", return_value=pack):
        result = await run_chat_with_context(graph, "anything", "test-model", top_k=5)

    assert "I do not have enough evidence" in result["answer"]


@pytest.mark.asyncio
async def test_citation_label_normalization_brackets() -> None:
    from app.intelligence.chat import make_chat_graph, run_chat_with_context

    capsule_id = uuid.uuid4()
    sf = _make_session_factory(rows=[_capsule_row(capsule_id)])
    # LLM returns bracketed label [C1] — must normalize to C1
    client = _make_client(answer="Answer.", citations=["[C1]"])
    embedder = _make_embedder()
    pack = _make_pack()

    graph = make_chat_graph(sf, client, embedder)
    with patch("app.intelligence.chat.load_pack", return_value=pack):
        result = await run_chat_with_context(graph, "test", "test-model", top_k=1)

    assert len(result["citations"]) == 1
    assert str(result["citations"][0]["capsule_id"]) == str(capsule_id)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/intelligence/test_chat_graph.py -v
```

Expected: ERRORS on `_run_retrieve_capsules`, `make_chat_graph` changes, `run_chat_with_context` changes.

- [ ] **Step 4: Rewrite `app/intelligence/chat.py`**

Replace the full file content with:

```python
# app/intelligence/chat.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Document, SemanticCapsule
from app.domain_packs.loader import load_pack
from app.intelligence.llm_client import LLMNetworkError
from app.intelligence.prompts.chat_answer import SYSTEM_PROMPT, build_user_prompt
from app.intelligence.prompts.classify_intent import (
    SYSTEM_PROMPT as _INTENT_SYSTEM_PROMPT,
    IntentClassification,
    build_classify_prompt,
)
from app.observability.run_context import chat_run


class ChatAnswerOutput(BaseModel):
    answer: str
    citations: list[str]


class ChatCitation(BaseModel):
    document_id: uuid.UUID
    capsule_id: uuid.UUID
    document_title: str | None
    url: str | None
    score: float
    object_type: str | None
    object_family: str | None
    lifecycle_state: str | None
    summary: str


class ChatState(TypedDict):
    question: str
    top_k: int
    model: str
    run_id: uuid.UUID | None
    query_intent: str
    pack: Any
    context_blocks: list[dict[str, Any]]
    answer: str
    citation_labels: list[str]
    citations: list[dict[str, Any]]
    tokens_used: int
    error: str | None


INSUFFICIENT_EVIDENCE_ANSWER = (
    "I do not have enough evidence to answer that from the current corpus."
)

_PRIORITY_SCORES = [1.0, 0.5, 0.25, 0.1]


def _normalize_citation_label(label: str) -> str:
    return label.strip().removeprefix("[").removesuffix("]").strip()


def compute_hybrid_score(
    candidate: dict,
    weights: dict[str, float],
    retrieval_priorities: list[str],
    recency_min: datetime,
    recency_max: datetime,
) -> float:
    """Telos-aware hybrid score. relation_relevance and evidence_quality are stubbed at 0."""
    sem = candidate["semantic_sim"] * weights.get("semantic_similarity", 0.0)

    if not retrieval_priorities:
        dom_score = 0.5
    else:
        family = candidate["object_family"]
        try:
            rank = retrieval_priorities.index(family)
            dom_score = _PRIORITY_SCORES[rank] if rank < len(_PRIORITY_SCORES) else 0.1
        except ValueError:
            dom_score = 0.0
    dom = dom_score * weights.get("domain_object_type_match", 0.0)

    auth = 0.5 * weights.get("source_authority", 0.0)

    created_at = candidate["created_at"]
    if recency_min == recency_max:
        rec_score = 0.5
    else:
        span = (recency_max - recency_min).total_seconds()
        rec_score = (created_at - recency_min).total_seconds() / span
        rec_score = max(0.0, min(1.0, rec_score))
    rec = rec_score * weights.get("recency", 0.0)

    sal = candidate["salience"] * weights.get("salience", 0.0)

    return sem + dom + auth + rec + sal


async def _run_classify_intent(state: dict, client: Any) -> dict:
    pack = state.get("pack")
    if pack is None:
        return {"query_intent": "general"}
    intent_names = list(pack.retrieval_policy.query_intents.keys())
    if not intent_names:
        return {"query_intent": "general"}
    try:
        result, _ = await client.complete_json(
            model=state["model"],
            system=_INTENT_SYSTEM_PROMPT,
            user=build_classify_prompt(state["question"], intent_names),
            response_model=IntentClassification,
            run_type="chat_classify_intent",
        )
        intent = result.intent if result.intent in intent_names else "general"
    except LLMNetworkError:
        intent = "general"
    return {"query_intent": intent}


async def _run_retrieve_capsules(
    state: dict,
    session_factory: async_sessionmaker,
    embedder: Any,
) -> dict:
    async with session_factory() as session:
        sentinel = await session.scalar(
            select(SemanticCapsule).where(SemanticCapsule.embedding.isnot(None)).limit(1)
        )
        if sentinel is None:
            return {"context_blocks": []}

        query_vec = embedder.embed_one(state["question"])
        distance = SemanticCapsule.embedding.cosine_distance(query_vec)
        fetch_k = state["top_k"] * 3
        rows = (
            await session.execute(
                select(
                    SemanticCapsule.id,
                    SemanticCapsule.document_id,
                    SemanticCapsule.text,
                    SemanticCapsule.domain_object_type,
                    SemanticCapsule.object_family,
                    SemanticCapsule.lifecycle_state,
                    SemanticCapsule.salience,
                    SemanticCapsule.created_at,
                    (1 - distance).label("semantic_sim"),
                    Document.title.label("title"),
                    Document.url.label("url"),
                )
                .join(Document, SemanticCapsule.document_id == Document.id)
                .where(SemanticCapsule.embedding.isnot(None))
                .order_by(distance)
                .limit(fetch_k)
            )
        ).all()

    pack = state.get("pack")
    query_intent = state.get("query_intent", "general")
    retrieval_priorities: list[str] = []
    if pack is not None and query_intent != "general":
        intent_cfg = pack.retrieval_policy.query_intents.get(query_intent, {})
        retrieval_priorities = intent_cfg.get("retrieval_priorities", [])

    weights: dict[str, float] = {}
    if pack is not None:
        weights = dict(pack.retrieval_policy.hybrid_score_weights)

    if rows:
        created_ats = [r.created_at for r in rows]
        recency_min: datetime = min(created_ats)
        recency_max: datetime = max(created_ats)
    else:
        now = datetime.now(timezone.utc)
        recency_min = recency_max = now

    candidates = [
        {
            "id": r.id,
            "document_id": r.document_id,
            "text": r.text,
            "object_type": r.domain_object_type,
            "object_family": r.object_family,
            "lifecycle_state": r.lifecycle_state,
            "salience": r.salience,
            "created_at": r.created_at,
            "semantic_sim": float(r.semantic_sim),
            "title": r.title,
            "url": r.url,
        }
        for r in rows
    ]

    scored = sorted(
        ((c, compute_hybrid_score(c, weights, retrieval_priorities, recency_min, recency_max)) for c in candidates),
        key=lambda x: x[1],
        reverse=True,
    )
    top = scored[: state["top_k"]]

    blocks = [
        {
            "label": f"C{i}",
            "document_id": c["document_id"],
            "capsule_id": c["id"],
            "document_title": c["title"],
            "url": c["url"],
            "score": score,
            "text": c["text"],
            "object_type": c["object_type"],
            "object_family": c["object_family"],
            "lifecycle_state": c["lifecycle_state"],
        }
        for i, (c, score) in enumerate(top, start=1)
    ]
    return {"context_blocks": blocks}


def make_chat_graph(session_factory: async_sessionmaker, client: Any, embedder: Any):
    async def classify_intent(state: ChatState) -> dict:
        return await _run_classify_intent(state, client)

    async def retrieve_capsules(state: ChatState) -> dict:
        return await _run_retrieve_capsules(state, session_factory, embedder)

    async def generate_answer(state: ChatState) -> dict:
        if not state.get("context_blocks"):
            return {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "citation_labels": [], "tokens_used": 0}
        user = build_user_prompt(state["question"], state["context_blocks"])
        try:
            result, tokens = await client.complete_json(
                model=state["model"],
                system=SYSTEM_PROMPT,
                user=user,
                response_model=ChatAnswerOutput,
                run_type="chat_answer",
            )
        except LLMNetworkError as exc:
            return {"error": str(exc), "tokens_used": 0}
        return {"answer": result.answer, "citation_labels": result.citations, "tokens_used": tokens}

    async def format_result(state: ChatState) -> dict:
        blocks_by_label = {block["label"]: block for block in state.get("context_blocks", [])}
        citation_labels = list(
            dict.fromkeys(
                _normalize_citation_label(lbl) for lbl in state.get("citation_labels", [])
            )
        )
        citations: list[dict[str, Any]] = []
        for label in citation_labels:
            block = blocks_by_label.get(label)
            if block is None:
                continue
            citations.append(
                ChatCitation(
                    document_id=block["document_id"],
                    capsule_id=block["capsule_id"],
                    document_title=block.get("document_title"),
                    url=block.get("url"),
                    score=block["score"],
                    object_type=block.get("object_type"),
                    object_family=block.get("object_family"),
                    lifecycle_state=block.get("lifecycle_state"),
                    summary=block["text"],
                ).model_dump()
            )
        if state.get("context_blocks") and not citations:
            return {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "citations": []}
        return {"answer": state.get("answer") or INSUFFICIENT_EVIDENCE_ANSWER, "citations": citations}

    def route_after_retrieve(state: ChatState) -> str:
        return "generate_answer" if state.get("context_blocks") else "format_result"

    builder = StateGraph(ChatState)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("retrieve_capsules", retrieve_capsules)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("format_result", format_result)

    builder.set_entry_point("classify_intent")
    builder.add_edge("classify_intent", "retrieve_capsules")
    builder.add_conditional_edges(
        "retrieve_capsules",
        route_after_retrieve,
        {"generate_answer": "generate_answer", "format_result": "format_result"},
    )
    builder.add_edge("generate_answer", "format_result")
    builder.add_edge("format_result", END)

    return builder.compile()


async def run_chat_with_context(
    graph: Any,
    question: str,
    model: str,
    *,
    top_k: int,
    pack: Any = None,
) -> dict:
    if pack is None:
        from app.config import settings
        pack = load_pack(settings.default_pack_id)
    async with chat_run() as run_id:
        final = await graph.ainvoke(
            {
                "question": question,
                "top_k": top_k,
                "model": model,
                "run_id": run_id,
                "query_intent": "",
                "pack": pack,
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

- [ ] **Step 5: Update `app/intelligence/prompts/chat_answer.py`**

Replace `build_user_prompt` to use capsule block format (remove span/claim sections):

```python
# app/intelligence/prompts/chat_answer.py
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
        blocks.append(
            "\n".join(
                [
                    f"[{block['label']}]",
                    f"Title: {block.get('document_title') or '(untitled)'}",
                    f"URL: {block.get('url') or '(none)'}",
                    f"Object type: {block.get('object_type') or '(unknown)'}",
                    f"Score: {block['score']:.3f}",
                    "Capsule:",
                    block["text"],
                ]
            )
        )
    return "\n\n".join(["Question:", question, "Context:", "\n\n".join(blocks)])
```

- [ ] **Step 6: Run all new tests**

```bash
pytest tests/intelligence/test_chat_intent.py tests/intelligence/test_chat_scoring.py tests/intelligence/test_chat_graph.py -v
```

Expected: all 15 tests PASSED

- [ ] **Step 7: Run the existing chat API tests to check no regressions**

```bash
pytest tests/test_chat_api.py -v
```

If any tests reference `span_id` or `claim_ids` in the `ChatCitation` shape, update them to use `capsule_id` and `summary`. Expected: all pass.

- [ ] **Step 8: Run pre-commit**

```bash
pre-commit run --all-files
```

- [ ] **Step 9: Commit config + chat.py rewrite**

```bash
git add app/config.py
git commit -m "feat(config): add default_pack_id setting"

git add app/intelligence/chat.py app/intelligence/prompts/chat_answer.py tests/intelligence/test_chat_graph.py
git commit -m "feat(chat): rewrite graph to capsule retrieval with telos-aware hybrid scoring"
```

---

## Task 5: Frontend — `ChatCitation` type + `CitationList` component

**Files:**
- Modify: `web/src/api/client.ts`
- Modify: `web/src/components/CitationList.tsx`
- Modify: `web/src/test/components.test.tsx`

Run frontend tests with: `cd web && npm test -- --run` (Vitest)

- [ ] **Step 1: Update `ChatCitation` type in `client.ts`**

Replace the existing `ChatCitation` type (lines 18–25):

```typescript
export type ChatCitation = {
  document_id: string
  capsule_id: string
  document_title: string | null
  url: string | null
  score: number
  object_type: string | null
  object_family: string | null
  lifecycle_state: string | null
  summary: string
}
```

- [ ] **Step 2: Update `CITATION` fixture in `components.test.tsx`**

Replace the existing `CITATION` constant (around line 37):

```typescript
const CITATION: ChatCitation = {
  document_id: 'doc-uuid-1234',
  capsule_id: 'cap-uuid-5678',
  document_title: 'Release article',
  url: 'https://example.com/release',
  score: 0.91,
  object_type: 'model_release',
  object_family: 'technical_objects',
  lifecycle_state: 'active',
  summary: 'GPT-5 released with 128k context window.',
}
```

- [ ] **Step 3: Update `CitationList` assertions in `components.test.tsx`**

Replace the `describe('CitationList', ...)` block:

```typescript
describe('CitationList', () => {
  it('renders nothing when citations are empty', () => {
    const { container } = render(<CitationList citations={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders object-type badge, score, host, and truncated summary', () => {
    render(<CitationList citations={[CITATION]} />)
    expect(screen.getByText('Release article')).toBeInTheDocument()
    expect(screen.getByText('0.91')).toBeInTheDocument()
    expect(screen.getByText('example.com')).toBeInTheDocument()
    expect(screen.getByText('MODEL_RELEASE')).toBeInTheDocument()
    expect(screen.getByText(/GPT-5 released/)).toBeInTheDocument()
  })

  it('shows lifecycle dot color for active state', () => {
    const { container } = render(<CitationList citations={[CITATION]} />)
    const dot = container.querySelector('.lifecycle-dot')
    expect(dot).toHaveClass('bg-green-500')
  })
})
```

- [ ] **Step 4: Run failing tests**

```bash
cd web && npm test -- --run
```

Expected: `CitationList` tests FAIL (component not updated yet)

- [ ] **Step 5: Rewrite `CitationList.tsx`**

```tsx
// web/src/components/CitationList.tsx
import { useState } from 'react'
import type { ChatCitation } from '../api/client'

type Props = {
  citations: ChatCitation[]
}

function shortId(id: string): string {
  return id.slice(0, 8)
}

function urlHost(url: string | null): string {
  if (!url) return '—'
  try {
    return new URL(url).hostname
  } catch {
    return url.slice(0, 40)
  }
}

function lifecycleDotClass(state: string | null): string {
  if (state === 'active' || state === 'confirmed') return 'bg-green-500'
  if (state === 'candidate') return 'bg-amber-400'
  return 'bg-gray-400'
}

export function CitationList({ citations }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null)

  if (citations.length === 0) return null

  return (
    <div className="mt-2 border border-gray-200 rounded text-xs">
      <p className="px-3 py-1.5 text-gray-500 font-medium border-b border-gray-200">
        Citations
      </p>
      {citations.map((c) => (
        <div key={c.capsule_id} className="border-b border-gray-100 last:border-0">
          <button
            onClick={() => setExpanded(expanded === c.capsule_id ? null : c.capsule_id)}
            className="w-full text-left px-3 py-1.5 hover:bg-gray-50 flex items-center gap-2"
          >
            <span
              className={`lifecycle-dot inline-block w-2 h-2 rounded-full flex-shrink-0 ${lifecycleDotClass(c.lifecycle_state)}`}
            />
            {c.object_type && (
              <span className="bg-blue-100 text-blue-700 rounded px-1 py-0.5 uppercase tracking-wide text-[10px] flex-shrink-0">
                {c.object_type}
              </span>
            )}
            <span className="font-medium text-gray-700 truncate flex-1">
              {c.document_title ?? shortId(c.document_id)}
            </span>
            <span className="text-gray-500 tabular-nums">{c.score.toFixed(2)}</span>
            <span className="text-gray-400 truncate max-w-32">{urlHost(c.url)}</span>
          </button>

          {expanded === c.capsule_id && (
            <div className="px-3 py-2 bg-gray-50 text-gray-600 space-y-1">
              <p className="line-clamp-3">{c.summary}</p>
              {c.url && (
                <p>
                  URL:{' '}
                  <a href={c.url} className="text-blue-600 underline break-all" target="_blank" rel="noreferrer">
                    {c.url}
                  </a>
                </p>
              )}
              <p>Capsule: <span className="font-mono">{c.capsule_id}</span></p>
              <p>Document: <span className="font-mono">{c.document_id}</span></p>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 6: Run all frontend tests**

```bash
cd web && npm test -- --run
```

Expected: all tests PASSED

- [ ] **Step 7: Pre-commit and commit**

```bash
cd <repo_root>
pre-commit run --all-files
git add web/src/api/client.ts web/src/components/CitationList.tsx web/src/test/components.test.tsx
git commit -m "feat(web): update ChatCitation type and CitationList with capsule cards"
```

---

## Task 6: Update validation harness slow test

**Files:**
- Modify: `tests/test_validation_harness.py`

- [ ] **Step 1: Find the semantic search test**

Open `tests/test_validation_harness.py`. Find `test_semantic_search_path` (currently around line 188). It monkeypatches an HTTP response containing `span_id`.

- [ ] **Step 2: Update the mock response shape**

Replace the mock response dict inside `test_semantic_search_path` from:

```python
return [
    {
        "span_id": str(uuid.uuid4()),
        "document_id": str(uuid.uuid4()),
        "span_index": 0,
        "score": 0.88,
        ...
    }
]
```

to match the new capsule-based search response (or update the assertion to check for whatever the patched endpoint now returns — the key assertion is that the CLI command succeeds and the output contains `capsule_id` or the relevant new field from `/search` if that endpoint is separate from chat).

> **Implementation note:** `test_semantic_search_path` tests the `nexus search` CLI command, not `/chat/answer`. If `nexus search` still uses span-based search, only update the assertion to match actual behavior. If it calls `/chat/answer`, update the mock to include `capsule_id` instead of `span_id`. Read the current test in full before editing.

- [ ] **Step 3: Run the slow test in isolation (requires live DB)**

```bash
pytest tests/test_validation_harness.py::test_semantic_search_path -v -m slow
```

Expected: PASSED (or skip if DB not available — mark as expected skip in CI)

- [ ] **Step 4: Pre-commit and commit**

```bash
pre-commit run --all-files
git add tests/test_validation_harness.py
git commit -m "test: update validation harness semantic search assertion for capsule retrieval"
```

---

## Final verification

- [ ] Run all pure unit tests

```bash
pytest tests/intelligence/test_chat_intent.py tests/intelligence/test_chat_scoring.py tests/intelligence/test_chat_graph.py -v
```

Expected: 15 PASSED

- [ ] Run the full fast suite

```bash
pytest -m "not slow" -v
```

Expected: all existing tests still pass; no regressions in `test_chat_api.py` or other chat tests.

- [ ] Run frontend tests

```bash
cd web && npm test -- --run
```

Expected: all PASSED

- [ ] Check migration applied

```bash
alembic current
```

Expected: `0006 (head)`
