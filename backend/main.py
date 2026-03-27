"""
myCloud — FastAPI Application Entry Point.

Configures CORS, registers routers, and starts background workers.
"""

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from api import uploads, auth
from services.worker import start_worker
from services import share_service
from database import get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle hooks."""
    await start_worker()
    yield
    # Shutdown: clean up resources if needed


app = FastAPI(
    title="myCloud",
    description="High-performance resumable file transfer service",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Upload-Offset", "X-Missing-Chunks"],
)

# ── Routers ───────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(uploads.router)


# ── Health ────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok"}


# ── Share Link Resolution ─────────────────────────────────────────────
@app.get("/s/{slug}", include_in_schema=False)
async def resolve_share(slug: str):
    """
    Top-level share link resolution.
    Must be here (not in /uploads router) so that /s/{slug} matches the
    share_url returned to clients.
    """
    async for db in get_db():
        token, status_code = await share_service.resolve_share_link(db, slug)
        if status_code == "OK":
            return RedirectResponse(url=f"/uploads/download/{token}")
        if status_code == "EXPIRED":
            raise HTTPException(status_code=410, detail="Share link has expired")
        if status_code == "LIMIT_REACHED":
            raise HTTPException(status_code=403, detail="Download limit reached for this link")
        raise HTTPException(status_code=404, detail="Share link not found")
