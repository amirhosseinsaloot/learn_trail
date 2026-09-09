"""The app factory serves /health and wraps every error in the envelope."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nuroli.main import create_app

ENVELOPE_KEYS = {"code", "message", "details", "retryable"}


def test_health_returns_ok_without_touching_dependencies() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_route_returns_not_found_envelope() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert set(error) == ENVELOPE_KEYS
    assert error["code"] == "not_found"
    assert error["retryable"] is False


def test_unexpected_error_returns_internal_error_without_details() -> None:
    app: FastAPI = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("database password is hunter2")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    error = response.json()["error"]
    assert set(error) == ENVELOPE_KEYS
    assert error["code"] == "internal_error"
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text
