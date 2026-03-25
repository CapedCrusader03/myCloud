import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgrespassword@db:5432/mycloud")

@pytest_asyncio.fixture
async def db():
    """Provides an async database connection for tests."""
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()
