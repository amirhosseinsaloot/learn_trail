"""Phase 0 contract for the ASGI app object (`api.main:app`).

Two things are worth asserting before a single route exists:

1. The app exposes *nothing* beyond FastAPI's built-in documentation routes.
   "No routes in Phase 0" (plans/phase-0.md) stays a checked claim rather than
   a comment, and the assertion is exact so it fails the moment a route lands.
   Phase 1's first chat/message endpoints must update it — that is the point.
2. The OpenAPI document builds. `/openapi.json` is the backend healthcheck
   target for docker-compose (plans/phase-0.md task 8, which explicitly rules
   out adding a health endpoint), so a schema that cannot be generated would
   break the Phase 0 exit criterion.
"""

from typing import Any

from starlette.routing import Route

from api.main import app

# What FastAPI mounts on its own for a default app: the schema document, the two
# doc UIs, and Swagger's OAuth2 redirect helper. (That last one exists on every
# FastAPI app; it is not auth — LearnTrail has none, CLAUDE.md invariant #1.)
FASTAPI_BUILTIN_PATHS = frozenset({"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"})


def test_app_exposes_only_fastapi_builtin_routes() -> None:
    # Checked separately from the path comparison below: `Route` is the only
    # route type with a `.path`, so a Mount or WebSocketRoute would otherwise
    # be filtered out of the comparison and pass unnoticed.
    assert all(isinstance(route, Route) for route in app.routes), (
        "Phase 0 defines no mounts and no websocket routes"
    )
    paths = {route.path for route in app.routes if isinstance(route, Route)}
    assert paths == set(FASTAPI_BUILTIN_PATHS)


def test_openapi_document_builds_and_declares_no_operations() -> None:
    schema: dict[str, Any] = app.openapi()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "LearnTrail API"
    # FastAPI's own doc routes are excluded from the schema, so with no
    # application routes this is the empty mapping.
    assert schema["paths"] == {}
