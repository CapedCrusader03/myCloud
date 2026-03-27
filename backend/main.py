from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from api import uploads
from services.worker import start_worker
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the background worker
    await start_worker()
    yield
    # Shutdown: Clean up resources if needed

app = FastAPI(lifespan=lifespan)

# Essential CORS for the React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # CRITICAL: Expose these so the React app can read them during HEAD requests
    expose_headers=["Upload-Offset", "X-Missing-Chunks"]
)

from api import uploads, auth

app.include_router(auth.router)
app.include_router(uploads.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}

# Top-level share link resolution — must be here (not in /uploads router) 
# so that the URL /s/{slug} matches the share_url returned to clients
@app.get("/s/{slug}", include_in_schema=False)
async def resolve_share(slug: str):
    from fastapi import HTTPException
    from fastapi.responses import RedirectResponse
    from services import upload_service
    from database import get_db
    from sqlalchemy.ext.asyncio import AsyncSession
    
    async for db in get_db():
        token, status = await upload_service.resolve_share_link(db, slug)
        if status == "OK":
            return RedirectResponse(url=f"/uploads/download/{token}")
        if status == "EXPIRED":
            raise HTTPException(status_code=410, detail="Share link has expired")
        if status == "LIMIT_REACHED":
            raise HTTPException(status_code=403, detail="Download limit reached for this link")
        raise HTTPException(status_code=404, detail="Share link not found")
