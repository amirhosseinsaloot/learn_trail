"""Contract for the ASGI app object (`api.main:app`).

Two things are worth asserting about the app itself, independent of what any
handler does:

1. The route table is exactly what we think it is. The comparison is exact, so a
   route added without a thought — or a path accidentally renamed — fails here
   rather than being discovered by the frontend.
2. The OpenAPI document builds. `/openapi.json` is the backend's docker-compose
   healthcheck target, so a schema that cannot be generated takes the whole
   stack down; and from Phase 1 it is also the input to openapi-typescript, so
   the frontend's types are only as good as this document.
"""

from typing import Any

from api.main import app

# The Phase 1 chat surface (docs/SPEC.md §6), path -> the verbs it answers.
# Asserted exactly, including the methods: an accidentally-added verb on an
# existing path is exactly the kind of thing a path-only comparison misses.
# Adding an endpoint is meant to fail this test — that is how a surface change
# stays a decision rather than a side effect.
CHAT_OPERATIONS = {
    "/chats": ["get", "post"],
    "/chats/{chat_id}": ["delete", "get", "patch"],
    "/chats/{chat_id}/restore": ["post"],
    "/chats/{chat_id}/messages": ["post"],
    # Sending a message and streaming the answer are separate endpoints, as
    # docs/SPEC.md §6 lists them.
    "/chats/{chat_id}/answer": ["post"],
    # Phase 3: the approval gate. Note there is no endpoint that creates a
    # `learning` directly — the only route to one is approving a draft, which is
    # CLAUDE.md invariant #5 visible in the URL space itself.
    "/chats/{chat_id}/summary": ["get", "post"],
    "/summaries/{draft_id}": ["patch"],
    "/summaries/{draft_id}/approve": ["post"],
    "/summaries/{draft_id}/reject": ["post"],
    # Phase 8: retrieval over the approved library. All three are POST — the
    # question is user content of unbounded length and belongs in a body, not in
    # a URL that ends up in logs and browser history.
    #
    # Note what is absent: no endpoint retrieves over `summary_draft`. Indexing
    # drafts would let unapproved model output supply the context for an answer,
    # which is CLAUDE.md invariant #5 defeated by the back door — and, like the
    # missing "create a learning" endpoint above, the absence is visible here.
    "/learnings/search": ["post"],
    "/learnings/ask": ["post"],
    "/learnings/reindex": ["post"],
    "/learnings": ["get"],
    "/learnings/{learning_id}": ["delete", "get", "patch"],
    "/learnings/{learning_id}/restore": ["post"],
}


def test_openapi_document_describes_exactly_the_chat_surface() -> None:
    """Asserted through the OpenAPI document rather than by walking `app.routes`.

    Two reasons, and the second is why this test was rewritten: the document is
    the actual contract (openapi-typescript generates the frontend's types from
    it, so a drift here is a frontend compile error), and as of FastAPI 0.140
    `include_router` no longer flattens routes into `app.routes` — it inserts a
    private `_IncludedRouter` wrapper, so enumerating `app.routes` finds only
    FastAPI's four built-in doc routes and would pass while asserting nothing.
    """
    schema: dict[str, Any] = app.openapi()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "LearnTrail API"

    # FastAPI's own doc routes (/docs, /redoc, /openapi.json,
    # /docs/oauth2-redirect) are excluded from the schema, so this is exactly the
    # application surface. That last one exists on every FastAPI app; it is not
    # auth — LearnTrail has none (CLAUDE.md invariant #1), which the security
    # test below enforces.
    operations = {path: sorted(methods) for path, methods in schema["paths"].items()}
    assert operations == CHAT_OPERATIONS


def test_no_endpoint_declares_a_security_scheme() -> None:
    """CLAUDE.md invariant #1, asserted at the HTTP boundary.

    Phase-independent, like its counterpart in packages/database: it is vacuously
    true today and must still hold in Phase 12. If auth is ever added by
    accident — a stray `Depends(oauth2_scheme)`, a copied snippet — FastAPI
    records it in the OpenAPI document and this fails.
    """
    schema: dict[str, Any] = app.openapi()
    assert "securitySchemes" not in schema.get("components", {})
    offenders = {
        f"{method.upper()} {path}"
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
        if operation.get("security")
    }
    assert offenders == set(), f"no endpoint may require auth; found {sorted(offenders)}"
