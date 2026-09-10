"""Liveness and readiness (ARCHITECTURE.md section 6.1).

``/health`` touches no dependency. ``/ready`` checks database connectivity
and that Alembic's recorded revision equals the head shipped with this build;
Compose healthchecks and the reverse proxy rely on both.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette import status

from nuroli.platform.db import check_connectivity, current_revision

router = APIRouter(tags=["platform"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    engine = request.app.state.engine
    if not await check_connectivity(engine):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "database": "unavailable", "migrations": "unknown"},
        )
    if await current_revision(engine) != request.app.state.migration_head:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "database": "ok", "migrations": "pending"},
        )
    return JSONResponse(content={"status": "ok", "database": "ok", "migrations": "current"})
