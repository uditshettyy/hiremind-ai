"""SQLAlchemy engine/session, per ARCHITECTURE.md §4 (app/core/database.py).

Merge with the existing file if Person B or earlier scaffolding already added
one — this only needs to exist once, shared across all three modules.
"""
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Initialize database extensions and tables per ARCHITECTURE.md §3.1."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, closes it after the request."""
    async with async_session_maker() as session:
        yield session
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
