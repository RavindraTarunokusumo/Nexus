"""Session memory controller — wraps the grounded chat graph with LangGraph persistence."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

logger = logging.getLogger(__name__)

_MAX_HISTORY_CHARS = 2000


class _MemoryState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    top_k: int
    model: str
    chat_result: dict[str, Any] | None


def _build_history_context(prior_messages: list[AnyMessage]) -> str:
    lines: list[str] = []
    total = 0
    for msg in reversed(prior_messages):
        if isinstance(msg, HumanMessage):
            line = f"User: {msg.content}"
        elif isinstance(msg, AIMessage):
            content = msg.content
            if len(content) > 400:
                content = content[:400] + "..."
            line = f"Assistant: {content}"
        else:
            continue
        if total + len(line) > _MAX_HISTORY_CHARS:
            break
        lines.append(line)
        total += len(line)
    return "\n".join(reversed(lines))


def make_memory_graph(chat_graph: Any, checkpointer: Any) -> Any:
    """Build a LangGraph memory graph that wraps the grounded chat graph."""

    async def chat_node(state: _MemoryState) -> dict[str, Any]:
        from app.intelligence.chat import run_chat_with_context

        # Find the last user message (the current turn)
        user_content = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        if not user_content:
            return {"chat_result": None}

        # Build conversation context from prior messages (all but last user message)
        prior = [m for m in state["messages"][:-1]]
        history_ctx = _build_history_context(prior)

        if history_ctx:
            enriched = f"Conversation history:\n{history_ctx}\n\nCurrent question: {user_content}"
        else:
            enriched = user_content

        try:
            result = await run_chat_with_context(
                chat_graph,
                enriched,
                state["model"],
                top_k=state["top_k"],
            )
        except Exception as exc:
            logger.error("session_memory: chat graph failed: %s", exc, exc_info=True)
            raise

        answer = result.get("answer", "")
        logger.info(
            "session_memory: turn complete",
            extra={"run_id": str(result.get("run_id")), "tokens": result.get("tokens_used")},
        )
        return {
            "messages": [AIMessage(content=answer)],
            "chat_result": result,
        }

    builder: StateGraph = StateGraph(_MemoryState)
    builder.add_node("chat", chat_node)
    builder.set_entry_point("chat")
    builder.add_edge("chat", END)
    return builder.compile(checkpointer=checkpointer)


async def invoke_with_memory(
    memory_graph: Any,
    thread_id: uuid.UUID,
    user_message: str,
    model: str,
    top_k: int = 8,
) -> dict[str, Any]:
    """Invoke the memory graph for one turn, keyed by session thread_id."""
    config = {"configurable": {"thread_id": str(thread_id)}}
    final = await memory_graph.ainvoke(
        {
            "messages": [HumanMessage(content=user_message)],
            "top_k": top_k,
            "model": model,
            "chat_result": None,
        },
        config=config,
    )
    return final.get("chat_result") or {}
