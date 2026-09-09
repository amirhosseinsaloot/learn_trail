"""Liveness endpoint (ARCHITECTURE.md section 6.1). It touches no dependency."""

from fastapi import APIRouter

router = APIRouter(tags=["platform"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
