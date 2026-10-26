"""Async SQLAlchemy engine + session factories.

Two distinct paths intentionally:

* The long-lived FastAPI app uses a module-level engine with a normal pool, accessed
  through the ``get_db`` dependency.
* Celery tasks run synchronous bodies that wrap ``asyncio.run(...)``; each run gets a
  fresh ``NullPool`` engine bound to *that* event loop. This avoids the classic
  "asyncpg connection attached to a different loop" failure you hit when reusing one
  pooled engine across many ``asyncio.run`` calls in a worker process.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def task_session() -> AsyncIterator[AsyncSession]:
    """Session for Celery tasks: a throwaway NullPool engine bound to the current loop."""
    task_engine = create_async_engine(settings.database_url, poolclass=NullPool, future=True)
    maker = async_sessionmaker(task_engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with maker() as session:
            yield session
    finally:
        await task_engine.dispose()
