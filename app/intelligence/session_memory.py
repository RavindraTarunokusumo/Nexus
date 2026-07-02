"""LangGraph-backed session memory controller.

Wraps the existing grounded chat graph in a stateful LangGraph graph that uses
AsyncPostgresSaver for per-session (thread) memory.  Each chat_session.id maps
to a LangGraph thread_id so prior turns are restored automatically on each
invocation.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from sqlalchemy.ext.asyncio import async_sessionmaker
from typing_extensions import TypedDict

from app.config import settings
from app.intelligence.chat import make_chat_graph, run_chat_with_context
from app.intelligence.llm_client import LLMClient

logger = logging.getLogger(__name__)


class _MemoryState(TypedDict):
    messages: Annotated[list, add_messages]
    answer_result: dict[str, Any] | None
    model: str
    top_k: int


def _to_psycopg_url(db_url: str) -> str:
    """Normalise any supported SQLAlchemy DB URL to a bare psycopg3 URL."""
    for dialect in ("postgresql+asyncpg://", "postgresql+psycopg2://"):
        if db_url.startswith(dialect):
            return "postgresql://" + db_url[len(dialect) :]
    return db_url


def _derive_title(text: str, max_len: int = 60) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len] + "..."


def make_memory_graph(chat_graph: Any, checkpointer: Any) -> Any:
    """Compile a memory-backed LangGraph wrapping *chat_graph*.

    The compiled graph persists conversation state via *checkpointer*.
    Pass the result to :func:`invoke_with_memory` to run a turn.
    """

    async def _answer_node(state: _MemoryState) -> dict:
        human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        q = str(human_msgs[-1].content)
        from app.intelligence.chat import run_chat_with_context

        model = state.get("model", "")
        top_k = state.get("top_k", 5)
        result = await run_chat_with_context(chat_graph, q, model, top_k=top_k)
        if result.get("error"):
            raise RuntimeError(f"Chat graph error: {result['error']}")
        ai_msg = AIMessage(content=result.get("answer", ""))
        return {"messages": [ai_msg], "answer_result": result}

    builder: StateGraph = StateGraph(_MemoryState)
    builder.add_node("answer", _answer_node)
    builder.set_entry_point("answer")
    builder.add_edge("answer", END)
    return builder.compile(checkpointer=checkpointer)


async def invoke_with_memory(
    *,
    memory_graph: Any,
    thread_id: uuid.UUID,
    user_message: str,
    model: str,
    top_k: int,
) -> dict[str, Any]:
    """Invoke one turn of a memory-backed graph compiled by :func:`make_memory_graph`.

    Returns the structured answer result dict from the grounded chat graph.
    Raises :class:`RuntimeError` on graph or checkpointer failure.
    """
    logger.info("session_turn.start session_id=%s", thread_id)
    try:
        final = await memory_graph.ainvoke(
            {
                "messages": [HumanMessage(content=user_message)],
                "answer_result": None,
                "model": model,
                "top_k": top_k,
            },
            config={"configurable": {"thread_id": str(thread_id)}},
        )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("session_turn.checkpointer_error session_id=%s error=%s", thread_id, exc)
        raise RuntimeError("Session memory unavailable.") from exc

    result = final.get("answer_result") or {}
    logger.info(
        "session_turn.done session_id=%s tokens=%s", thread_id, result.get("tokens_used", 0)
    )
    return result


async def run_session_turn(
    *,
    session_id: uuid.UUID,
    question: str,
    top_k: int,
    model: str,
    openrouter_api_key: str,
    db_url: str,
    session_factory: async_sessionmaker,
    embedder: Any,
) -> dict[str, Any]:
    """Invoke one turn of the memory-backed chat session.

    Persists the HumanMessage + AIMessage pair to the LangGraph checkpointer
    (keyed by session_id as thread_id) and returns the structured answer result
    from the grounded chat graph.

    Raises RuntimeError on checkpointer or graph failure — the caller (route)
    maps this to 503 and does not persist app-side messages.
    """
    psycopg_url = _to_psycopg_url(db_url)
    logger.info("session_turn.start session_id=%s", session_id)

    async def _answer_node(state: _MemoryState) -> dict:
        human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        q = str(human_msgs[-1].content)

        llm_client = LLMClient(
            settings.llm_api_key, session_factory, base_url=settings.llm_base_url
        )
        graph = make_chat_graph(session_factory, llm_client, embedder)
        try:
            result = await run_chat_with_context(graph, q, model, top_k=top_k)
        except Exception as exc:
            logger.error("session_turn.graph_error session_id=%s error=%s", session_id, exc)
            raise

        if result.get("error"):
            raise RuntimeError(f"Chat graph error: {result['error']}")
        ai_msg = AIMessage(content=result.get("answer", ""))
        return {"messages": [ai_msg], "answer_result": result}

    builder: StateGraph = StateGraph(_MemoryState)
    builder.add_node("answer", _answer_node)
    builder.set_entry_point("answer")
    builder.add_edge("answer", END)

    try:
        async with AsyncPostgresSaver.from_conn_string(psycopg_url) as checkpointer:
            await checkpointer.setup()
            agent = builder.compile(checkpointer=checkpointer)
            final = await agent.ainvoke(
                {"messages": [HumanMessage(content=question)], "answer_result": None},
                config={"configurable": {"thread_id": str(session_id)}},
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("session_turn.checkpointer_error session_id=%s error=%s", session_id, exc)
        raise RuntimeError("Session memory unavailable.") from exc

    result = final.get("answer_result") or {}
    logger.info(
        "session_turn.done session_id=%s tokens=%s", session_id, result.get("tokens_used", 0)
    )
    return result
