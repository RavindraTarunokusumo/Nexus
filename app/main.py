from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.session import make_engine, make_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory
    yield
    await engine.dispose()


app = FastAPI(title="Nexus Lite", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


from app.api.routes_sources import router as sources_router  # noqa: E402
from app.api.routes_ingestion import router as ingestion_router  # noqa: E402

app.include_router(sources_router)
app.include_router(ingestion_router)
