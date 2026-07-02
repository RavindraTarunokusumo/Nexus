"""Ad-hoc demo driver: run live chat answers with citations against a populated DB.

Not part of the benchmark; a thin wrapper to show the MemoryAgent answering with
evidence + role/epistemic annotations. Usage:
    DATABASE_URL=... python -m scripts.benchmarks.demo_answer "question one" "question two"
"""

from __future__ import annotations

import asyncio
import sys

from app.config import settings
from app.db.session import make_engine, make_session_factory
from app.intelligence.chat import make_chat_graph, run_chat_with_context
from app.intelligence.embedder import Embedder
from app.intelligence.llm_client import LLMClient


async def _main(questions: list[str]) -> None:
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    embedder = Embedder(settings.t1_model)
    client = LLMClient(settings.llm_api_key, session_factory, base_url=settings.llm_base_url)
    graph = make_chat_graph(session_factory, client, embedder)

    for q in questions:
        print("\n" + "=" * 78)
        print(f"Q: {q}")
        result = await run_chat_with_context(graph, q, settings.t2_model, top_k=5)
        print(f"\nA: {result['answer']}\n")
        cites = result.get("citations", [])
        if not cites:
            print("(no citations)")
        for c in cites:
            role = c.get("role") or "primary"
            print(f"  [{role}] {c.get('document_title') or '(untitled)'}")
            if c.get("epistemic_note"):
                print(f"        {c['epistemic_note']}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
