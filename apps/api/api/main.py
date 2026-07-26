"""ASGI application entrypoint: ``uvicorn api.main:app``.

Deliberately thin: this module owns the app object and the list of routers, and
nothing else. Route handlers live in `api.routers`, so this file does not grow as
the surface does.
"""

from fastapi import FastAPI

from api.routers import chats

app = FastAPI(
    title="LearnTrail API",
    version="0.1.0",
    summary="Single-user AI learning workspace. No auth, no users, by design.",
)

# No auth dependency, no middleware stack, no CORS config yet. CORS lands with
# the first browser fetch (the Phase 1 chat page); adding it before there is a
# caller would mean guessing the origin.
app.include_router(chats.router)
