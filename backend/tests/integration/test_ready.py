"""Readiness and migration-on-start against the real database (ARCHITECTURE.md section 6.1)."""

import asyncio
import os
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from tests.conftest import TEST_ENVIRONMENT

from nuroli.main import create_app
from nuroli.platform.cli import script_head
from nuroli.platform.db import UnitOfWork, get_unit_of_work
from nuroli.platform.settings import Settings, load_settings


async def test_ready_reports_ok_when_database_is_at_head(client: AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "migrations": "current"}


async def test_ready_is_503_when_the_database_is_unreachable() -> None:
    unreachable = load_settings(database_url="postgresql+asyncpg://nuroli:x@127.0.0.1:1/nuroli")
    app = create_app(unreachable)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            response = await http.get("/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unavailable",
        "migrations": "unknown",
    }


async def test_ready_is_503_while_migrations_are_pending(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]  # noqa: SLF001
    app.state.migration_head = "9999"
    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "ok", "migrations": "pending"}


async def test_health_never_touches_the_database() -> None:
    unreachable = load_settings(database_url="postgresql+asyncpg://nuroli:x@127.0.0.1:1/nuroli")
    app = create_app(unreachable)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            response = await http.get("/health")
    assert response.status_code == 200


async def test_unit_of_work_dependency_yields_the_request_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    app = client._transport.app  # type: ignore[attr-defined]  # noqa: SLF001
    request = type("Request", (), {"app": app})()
    generator = get_unit_of_work(request)  # type: ignore[arg-type]
    unit: UnitOfWork = await generator.__anext__()
    assert unit.session is db_session
    assert unit.committed is False
    with pytest.raises(StopAsyncIteration):
        await generator.__anext__()


async def test_citext_extension_exists_after_migration(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'citext'"))
    assert result.scalar() == 1


def _database_url_for(base_url: str, database: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", "", ""))


def test_two_migrate_processes_do_not_race(test_database_url: str, test_settings: Settings) -> None:
    """Two API containers starting together: both succeed, migrations apply once."""
    admin_url = _database_url_for(test_database_url, "nuroli")
    race_url = _database_url_for(test_database_url, f"nuroli_race_{os.getpid()}")
    race_db = race_url.rsplit("/", 1)[1]

    async def run_admin(statement: str) -> None:
        engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await connection.execute(text(statement))
        finally:
            await engine.dispose()

    asyncio.run(run_admin(f'DROP DATABASE IF EXISTS "{race_db}"'))
    asyncio.run(run_admin(f'CREATE DATABASE "{race_db}"'))
    env = {
        **os.environ,
        **TEST_ENVIRONMENT,
        "NUROLI_DATABASE_URL": race_url,
        "NUROLI_LOG_LEVEL": "info",
    }
    try:
        processes = [
            subprocess.Popen(  # noqa: S603
                [sys.executable, "-m", "nuroli.platform.cli", "migrate"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for _ in range(2)
        ]
        outputs = [process.communicate(timeout=120)[0] for process in processes]
        assert [process.returncode for process in processes] == [0, 0], outputs
        for output in outputs:
            assert f"database at revision {script_head()}" in output
            assert "migration lock acquired" in output

        async def revision_of_race_db() -> str | None:
            engine = create_async_engine(race_url)
            try:
                async with engine.connect() as connection:
                    row = (
                        await connection.execute(text("SELECT version_num FROM alembic_version"))
                    ).first()
            finally:
                await engine.dispose()
            return None if row is None else str(row[0])

        assert asyncio.run(revision_of_race_db()) == script_head()
    finally:
        asyncio.run(run_admin(f'DROP DATABASE IF EXISTS "{race_db}"'))
