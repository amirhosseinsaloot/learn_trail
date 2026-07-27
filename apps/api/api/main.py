"""ASGI application entrypoint: ``uvicorn api.main:app``.

Deliberately thin: this module owns the app object and the list of routers, and
nothing else. Route handlers live in `api.routers`, so this file does not grow as
the surface does.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.graph import lifespan
from api.routers import chats, knowledge

app = FastAPI(
    title="LearnTrail API",
    version="0.1.0",
    summary="Single-user AI learning workspace. No auth, no users, by design.",
    # Compiles the chat graph and opens its checkpointer for the process
    # (api/graph.py). From Phase 2 the application does not start without a
    # working graph — which is the point: the graph *is* the request path.
    lifespan=lifespan,
)

# The browser origin the chat page is served from. A list of one, from the
# environment, rather than `["*"]`: a wildcard would let any page on the machine
# drive this API — and this API spends money on model calls. There are no
# credentials to protect (CLAUDE.md invariant #1), so this is about who can make
# the app *act*, not about who can read a user's data.
ALLOWED_ORIGINS = [os.environ.get("WEB_ORIGIN") or "http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # No cookies, no Authorization header — there is no auth. Leaving credentials
    # off keeps the browser from ever attaching ambient state to these requests.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(chats.router)
app.include_router(knowledge.router)
