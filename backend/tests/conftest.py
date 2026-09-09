"""Shared fixtures. Configuration comes from fixtures, never from .env
(IMPLEMENTATION.md section 2.6)."""

from collections.abc import Iterator

import pytest

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
