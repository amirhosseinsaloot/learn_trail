"""FastAPI application factory.

Includes the platform routers and the three module routers exactly once.
Feature tickets add routes inside their module's ``api/router.py``; this file
is not edited by feature tickets (IMPLEMENTATION.md section 2.3).
"""

from fastapi import FastAPI

from nuroli.conversations.api.router import router as conversations_router
from nuroli.identity.api.router import router as identity_router
from nuroli.knowledge.api.router import router as knowledge_router
from nuroli.platform.errors import install_error_handlers
from nuroli.platform.health import router as health_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(title="Nuroli")
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(identity_router, prefix=API_PREFIX)
    app.include_router(conversations_router, prefix=API_PREFIX)
    app.include_router(knowledge_router, prefix=API_PREFIX)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    # One worker: rate limits and concurrency slots are in-memory (R-19).
    # Binding all interfaces is required inside the container.
    uvicorn.run("nuroli.main:app", host="0.0.0.0", port=8000, workers=1)  # noqa: S104
