"""Every response carries X-Request-Id; error envelopes include the id."""

import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from nuroli.main import create_app
from nuroli.platform.settings import load_settings

HEX_32 = re.compile(r"^[0-9a-f]{32}$")


def test_health_response_carries_a_request_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert HEX_32.match(response.headers["X-Request-Id"])


def test_error_envelope_and_header_carry_the_same_request_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert HEX_32.match(response.headers["X-Request-Id"])


def test_internal_error_envelope_includes_request_id_in_details() -> None:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("unexpected")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    request_id = response.headers["X-Request-Id"]
    assert response.json()["error"]["details"] == {"request_id": request_id}


def test_each_request_gets_a_distinct_id() -> None:
    with TestClient(create_app()) as client:
        first = client.get("/health").headers["X-Request-Id"]
        second = client.get("/health").headers["X-Request-Id"]
    assert first != second


def test_access_line_is_logged_with_route_template_and_request_id(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NUROLI_LOG_LEVEL", "info")
    app = create_app(load_settings())
    with TestClient(app) as client:
        response = client.get("/health")
    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    access = [line for line in lines if line["logger"] == "nuroli.request"]
    assert access[-1]["route"] == "/health"
    assert access[-1]["status"] == 200
    assert access[-1]["method"] == "GET"
    assert access[-1]["request_id"] == response.headers["X-Request-Id"]
    assert access[-1]["duration_ms"] >= 0
    startup = [line for line in lines if line["message"] == "starting"]
    assert startup[-1]["model_host"] == "localhost"
    assert startup[-1]["model_name"] == "fake-model"
    assert "model_api_key" not in startup[-1]
    logging.getLogger().handlers.clear()
