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

app.include_router(uploads.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
