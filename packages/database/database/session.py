"""Async engine and session factory for the request path.

Migrations run on a **sync** connection (migrations/env.py); requests run on an
**async** one. Both use the same `postgresql+psycopg` URL, because psycopg 3
serves both SQLAlchemy dialects — that is the whole reason this project picked it
over asyncpg + psycopg2 (see this package's pyproject.toml).

`sqlalchemy[asyncio]` is required, not plain `sqlalchemy`: `create_async_engine`
bridges sync ORM internals to async I/O through greenlet, which arrives only via
that extra. Without it this module imports fine and fails at first use, which is
the worst possible time to find out.

The engine is created lazily and cached. Creating it at import time would open a
connection pool as a side effect of importing the module — which breaks
`alembic`, `--help`, and any test that imports the package without a database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from database.config import database_url


@lru_cache(maxsize=1)
def engine() -> AsyncEngine:
    """The process-wide async engine, created on first use.

    `lru_cache` rather than a module-level global so tests can reset it with
    `engine.cache_clear()`; a connection pool must not be shared across event
    loops, and pytest gives each test its own.
    """
    return create_async_engine(
        database_url(),
        # Verify a pooled connection is still alive before handing it out.
        # Without this, a connection killed by a Postgres restart (or by
        # `make down && make up`) surfaces as a random failed request rather
        # than a reconnect — a real annoyance in local development.
        pool_pre_ping=True,
        # Recycle before Postgres' own idle timeouts can close a connection
        # underneath the pool.
        pool_recycle=1800,
    )


@lru_cache(maxsize=1)
def session_factory() -> async_sessionmaker[AsyncSession]:
    """Session factory bound to :func:`engine`."""
    return async_sessionmaker(
        engine(),
        # ORM objects stay usable after `commit()`. With the default
        # `expire_on_commit=True`, reading `chat.id` after committing triggers a
        # refresh — which, on an async session, is an implicit IO await in the
        # middle of building a response and raises MissingGreenlet.
        expire_on_commit=False,
        autoflush=False,
    )


async def session() -> AsyncIterator[AsyncSession]:
    """Yield one session per request, rolling back anything left uncommitted.

    Shaped as a FastAPI dependency (`Depends(session)`). The commit is the
    caller's decision, not this function's: a request that raises halfway
    through must not persist half its work, so the only thing guaranteed here is
    that the session is closed and any open transaction is discarded.
    """
    async with session_factory()() as active_session:
        try:
            yield active_session
        finally:
            # No-op after an explicit commit; discards the transaction otherwise.
            await active_session.rollback()
