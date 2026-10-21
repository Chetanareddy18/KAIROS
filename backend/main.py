import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.deps import require_api_key
from backend.api.ingest import router as ingest_router
from backend.api.routes import router
from backend.api.sources import router as sources_router
from backend.config import ROOT, settings
from backend.pipeline import KAIROSPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kairos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    for d in (settings.data_dir, settings.upload_dir, settings.transfer_dir):
        d.mkdir(parents=True, exist_ok=True)
    pipeline = KAIROSPipeline()
    pipeline.collector.load_sources_file()
    app.state.pipeline = pipeline

    # BackgroundScheduler runs the (blocking) pipeline in its own thread, so the API stays responsive
    scheduler = BackgroundScheduler(timezone="UTC")
    if settings.scheduler_enabled:
        scheduler.add_job(pipeline.run, "interval", minutes=settings.pipeline_interval_min,
                          id="kairos_pipeline", max_instances=1, coalesce=True)
        scheduler.start()
        logger.info("KAIROS pipeline scheduler started (every %d min)", settings.pipeline_interval_min)
    app.state.scheduler = scheduler if settings.scheduler_enabled else None
    yield
    if settings.scheduler_enabled:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="KAIROS API",
    description="Autonomous Causal Business Intelligence Agent",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_auth = [Depends(require_api_key)]
app.include_router(router,         prefix="/api/v1", dependencies=_auth)
app.include_router(sources_router, prefix="/api/v1", dependencies=_auth, tags=["sources"])
app.include_router(ingest_router,  prefix="/api/v1", dependencies=_auth, tags=["ingest"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "kairos"}


# Serve the built dashboard from the same container when it exists (single-service deploys)
_dist = ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (_dist / path).resolve()
        if path and candidate.is_file() and Path(_dist).resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
