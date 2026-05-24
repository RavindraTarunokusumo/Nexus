import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
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

    yield
    await engine.dispose()


app = FastAPI(title="Nexus Lite", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


from app.api.routes_chat import router as chat_router  # noqa: E402
from app.api.routes_claims import router as claims_router  # noqa: E402
from app.api.routes_documents import router as documents_router  # noqa: E402
from app.api.routes_ingestion import router as ingestion_router  # noqa: E402
from app.api.routes_sources import router as sources_router  # noqa: E402

app.include_router(sources_router)
app.include_router(ingestion_router)
app.include_router(documents_router)
app.include_router(claims_router)
app.include_router(chat_router)
