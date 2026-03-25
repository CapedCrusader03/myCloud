from fastapi import FastAPI
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

app.include_router(uploads.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
