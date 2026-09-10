"""Database access (IMPLEMENTATION.md section 2.3).

One async engine built from settings, a ``UnitOfWork`` wrapping one
``AsyncSession`` per request, and the FastAPI dependency that opens it.
Repositories receive the session through the unit of work; use cases call
``commit`` at the end. The database URL is never logged.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from fastapi import Request
from sqlalchemy import MetaData, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from nuroli.platform.settings import Settings

CONNECT_TIMEOUT_SECONDS = 5

# Deterministic constraint names so Alembic autogenerate and downgrades agree.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Declarative base every ``infrastructure/models.py`` extends."""

    metadata = metadata


class SessionLike(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def close(self) -> None: ...


class UnitOfWork:
    """One transaction per request. Whatever is not committed is rolled back on close."""

    def __init__(self, session: SessionLike) -> None:
        self.session = session
        self.committed = False

    async def commit(self) -> None:
        await self.session.commit()
        self.committed = True

    async def rollback(self) -> None:
        await self.session.rollback()
        self.committed = False

    async def close(self) -> None:
        try:
            if not self.committed:
                await self.session.rollback()
        finally:
            await self.session.close()


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"timeout": CONNECT_TIMEOUT_SECONDS},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_unit_of_work(request: Request) -> AsyncIterator[UnitOfWork]:
    """FastAPI dependency: one unit of work for the duration of the request."""
    session: AsyncSession = request.app.state.session_factory()
    unit = UnitOfWork(session)
    try:
        yield unit
    finally:
        await unit.close()


async def check_connectivity(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError, OSError, TimeoutError:
        return False
    return True


async def current_revision(engine: AsyncEngine) -> str | None:
    """Alembic's recorded revision, or None before the first migration ran."""
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).first()
    except SQLAlchemyError:
        return None
    return None if row is None else str(row[0])
