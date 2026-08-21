"""ASGI application entrypoint: ``uvicorn api.main:app``.

Deliberately thin: this module owns the app object and the list of routers, and
nothing else. Route handlers live in `api.routers`, so this file does not grow as
the surface does.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from ai_core.telemetry import configure_tracing
from api.graph import lifespan
from api.routers import chats, knowledge, models

# Before the app object exists, because the FastAPI instrumentor below binds to
# whatever tracer provider is global at instrumentation time. Configured here
# rather than in the lifespan for the same reason: the lifespan runs after the
# middleware stack is built.
#
# With no `OTEL_EXPORTER_OTLP_ENDPOINT` set this installs a provider that creates
# spans and exports nothing, which is what the test suite runs against — see
# ai_core/telemetry/tracing.py on why that is better than not tracing at all.
configure_tracing()

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

# One span per HTTP request, with method, route template and status code. Auto
# instrumentation rather than a hand-rolled middleware: getting the status code
# right on a *streaming* response is the fiddly part, and this already does it.
#
# The schema routes are excluded. `/openapi.json` is what the backend container's
# healthcheck probes every ten seconds (docker-compose.yml), and a trace store
# filling with liveness probes makes the real traces harder to find — which is
# the only thing it is for.
# `exclude_spans` is not optional here, it is the difference between a readable
# trace and an unusable one. The ASGI instrumentation emits one `http send` span
# per response chunk, and `/chats/{id}/answer` is SSE — a 36-token answer
# produced 37 spans, of which 30-odd said "a chunk was written" and buried the
# five that described what the system actually did.
FastAPIInstrumentor.instrument_app(
    app,
    excluded_urls="openapi.json,docs,redoc",
    exclude_spans=["send", "receive"],
)

app.include_router(chats.router)
app.include_router(knowledge.router)
app.include_router(models.router)
