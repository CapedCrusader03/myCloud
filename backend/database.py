"""
Database engine, session factory, and base model.

Connection parameters are sourced from config.settings.
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Detect stale connections before use
)

# AsyncSession factory
async_session = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


# All models will inherit from this Base
class Base(DeclarativeBase):
    pass


# FastAPI Dependency to get the DB session in your routes
async def get_db():
    async with async_session() as session:
        yield session
