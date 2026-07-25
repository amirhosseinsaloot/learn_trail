"""ASGI application entrypoint: ``uvicorn api.main:app``.

Phase 0 defines **no routes** — not even a health endpoint. The deliverable is
an app object that imports and boots, giving Ruff and mypy real code to check.
Routers arrive in Phase 1 with the first chat and message endpoints
(docs/SPEC.md §6, §15).
"""

from fastapi import FastAPI

app = FastAPI(
    title="LearnTrail API",
    version="0.1.0",
    summary="Single-user AI learning workspace. No auth, no users, by design.",
)
