import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.pipeline import KAIROSPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kairos")

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline = KAIROSPipeline()
    app.state.pipeline = pipeline
    scheduler.add_job(pipeline.run, "interval", minutes=15, id="kairos_pipeline")
    scheduler.start()
    logger.info("KAIROS pipeline scheduler started (every 15 min)")
    yield
    scheduler.shutdown()


app = FastAPI(
    title="KAIROS API",
    description="Autonomous Causal Business Intelligence Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://kairos-app.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "service": "kairos"}
