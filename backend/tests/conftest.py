"""Shared fixtures. Configuration comes from fixtures, never from .env
(IMPLEMENTATION.md section 2.6). Database fixtures need
NUROLI_TEST_DATABASE_URL, which `make test-integration` provides from the dev
stack (or CI from its PostgreSQL service); every test runs inside a
transaction that is rolled back afterwards."""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from nuroli.main import create_app
from nuroli.platform.cli import migrate
from nuroli.platform.db import create_engine
from nuroli.platform.settings import Settings, load_settings

TEST_ENVIRONMENT: dict[str, str] = {
    "NUROLI_PUBLIC_ORIGIN": "http://localhost:8080",
    "NUROLI_SECRET_KEY": "test-only-secret-key-0123456789abcdef0123456789",
    "NUROLI_DATABASE_URL": "postgresql+asyncpg://nuroli:test-only-db-password@localhost:5432/nuroli_test",
    "NUROLI_MODEL_BASE_URL": "http://localhost:9000/v1",
    "NUROLI_MODEL_NAME": "fake-model",
    "NUROLI_LOG_LEVEL": "warning",
}


@pytest.fixture(autouse=True, scope="session")
def test_environment() -> Iterator[dict[str, str]]:
    """A valid NUROLI_* environment for every test; individual tests override with monkeypatch."""
    with pytest.MonkeyPatch.context() as patch:
        for key, value in TEST_ENVIRONMENT.items():
            patch.setenv(key, value)
        yield TEST_ENVIRONMENT


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("NUROLI_TEST_DATABASE_URL", "")
    if not url:
        pytest.fail("NUROLI_TEST_DATABASE_URL is not set; run `make test-integration`")
    return url


@pytest.fixture(scope="session")
def test_settings(test_environment: dict[str, str], test_database_url: str) -> Settings:
    return load_settings(database_url=test_database_url)


@pytest.fixture(scope="session")
def migrated_database(test_settings: Settings) -> str:
    """The test database at the current Alembic head, once per session."""
    return asyncio.run(migrate(test_settings))


@pytest.fixture
async def db_engine(test_settings: Settings, migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(test_settings)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session inside an outer transaction that is rolled back after the test."""
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
async def client(
    test_settings: Settings, db_engine: AsyncEngine, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    """The application over ASGI with its unit of work bound to the test transaction."""
    app = create_app(test_settings)
    async with app.router.lifespan_context(app):
        app.state.engine = db_engine
        app.state.session_factory = lambda: db_session
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            yield http
