from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.database import init_db
from app.services.seed import seed_if_empty
from app.api.v1 import router as v1_router


setup_logging(settings.debug)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    inserted = await seed_if_empty()
    if inserted:
        import logging
        logging.getLogger(__name__).info(f"Seeded {inserted} sample researches")
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# Cache-Control middleware (before CORS)
from app.core.middleware import CacheControlMiddleware
app.add_middleware(CacheControlMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name, "agent_mode": settings.agent_mode}


app.include_router(v1_router, prefix="/api/v1")

# OpenAI-compatible endpoints are mounted at the root (no prefix) so callers
# can use /v1/models, /v1/runs directly as with the OpenAI REST API.
from app.api.v1.openai_compat import router as openai_compat_router
app.include_router(openai_compat_router)  # Routes already specify /v1/... paths
