import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.session import make_engine, make_session_factory
from app.observability.logger import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory

    try:
        from app.intelligence.embedder import Embedder

        app.state.embedder = Embedder(settings.t1_model)
        logger.info("Embedder loaded: %s", settings.t1_model)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedder unavailable (%s); search disabled.", exc)
        app.state.embedder = None

    # Initialise LangGraph Postgres checkpointer for session memory
    checkpointer_pool = None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool

        from app.intelligence.chat import make_chat_graph
        from app.intelligence.llm_client import LLMClient
        from app.intelligence.session_memory import make_memory_graph

        psycopg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        checkpointer_pool = AsyncConnectionPool(
            conninfo=psycopg_url, min_size=1, max_size=5, open=False
        )
        await checkpointer_pool.open()
        checkpointer = AsyncPostgresSaver(checkpointer_pool)
        await checkpointer.setup()
        app.state.checkpointer = checkpointer

        if app.state.embedder is not None:
            client = LLMClient(
                settings.llm_api_key, session_factory, base_url=settings.llm_base_url
            )
            chat_graph = make_chat_graph(session_factory, client, app.state.embedder)
            app.state.memory_graph = make_memory_graph(chat_graph, checkpointer)
            logger.info("Session memory initialised.")
        else:
            app.state.memory_graph = None
            logger.warning("Session memory disabled; embedder unavailable.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Session memory unavailable (%s).", exc)
        app.state.checkpointer = None
        app.state.memory_graph = None

    yield

    if checkpointer_pool is not None:
        await checkpointer_pool.close()
    await engine.dispose()


app = FastAPI(title="Nexus Lite", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


from app.api.routes_capsules import router as capsules_router  # noqa: E402
from app.api.routes_chat import router as chat_router  # noqa: E402
from app.api.routes_chat_sessions import router as chat_sessions_router  # noqa: E402
from app.api.routes_claims import router as claims_router  # noqa: E402
from app.api.routes_documents import router as documents_router  # noqa: E402
from app.api.routes_ingestion import router as ingestion_router  # noqa: E402
from app.api.routes_sources import router as sources_router  # noqa: E402
from app.api.routes_stats import router as stats_router  # noqa: E402

app.include_router(sources_router)
app.include_router(ingestion_router)
app.include_router(documents_router)
app.include_router(claims_router)
app.include_router(stats_router)
app.include_router(capsules_router)
app.include_router(chat_router)
app.include_router(chat_sessions_router)
