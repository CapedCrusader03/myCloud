import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgrespassword@db:5432/mycloud")

engine = create_async_engine(DATABASE_URL, echo=False)

# AsyncSession factory
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# All models will inherit from this Base
class Base(DeclarativeBase):
    pass

# FastAPI Dependency to get the DB session in your routes
async def get_db():
    async with async_session() as session:
        yield session
