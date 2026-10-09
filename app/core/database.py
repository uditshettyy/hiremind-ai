"""SQLAlchemy engine/session, per ARCHITECTURE.md §4 (app/core/database.py)."""
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

DATABASE_URL = os.getenv("DATABASE_URL") or settings.database_url

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async_session_maker = AsyncSessionLocal


class Base(DeclarativeBase):
    pass


import logging

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Initialize database extensions and tables."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        logger.warning("Database initialization skipped or failed: %s", exc)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, closes it after the request."""
    async with AsyncSessionLocal() as session:
        yield session
