"""FastAPI application factory.

Loads settings once (failing fast with every problem listed), configures
logging, installs the request-id middleware and error handlers, and includes
the platform routers and the three module routers exactly once. Feature
tickets add routes inside their module's ``api/router.py``; this file is not
edited by feature tickets (IMPLEMENTATION.md section 2.3).
"""

import logging
import sys

from fastapi import FastAPI

from nuroli.conversations.api.router import router as conversations_router
from nuroli.identity.api.router import router as identity_router
from nuroli.knowledge.api.router import router as knowledge_router
from nuroli.platform.errors import install_error_handlers
from nuroli.platform.health import router as health_router
from nuroli.platform.lifespan import lifespan
from nuroli.platform.logging import configure_logging
from nuroli.platform.middleware import RequestIdMiddleware
from nuroli.platform.settings import Settings, SettingsError, load_settings

API_PREFIX = "/api/v1"

log = logging.getLogger("nuroli")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else load_settings()
    configure_logging(settings)
    app = FastAPI(title="Nuroli", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(identity_router, prefix=API_PREFIX)
    app.include_router(conversations_router, prefix=API_PREFIX)
    app.include_router(knowledge_router, prefix=API_PREFIX)
    # The startup line names the model host and model name only, never a key.
    log.info(
        "starting", extra={"model_host": settings.model_host, "model_name": settings.model_name}
    )
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn nuroli.main:app` builds the app on first access, so importing this
    # module (for example from tests) does not require a configured environment.
    if name == "app":
        return create_app()
    raise AttributeError(name)


if __name__ == "__main__":
    import uvicorn

    try:
        application = create_app()
    except SettingsError as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
    # One worker: rate limits and concurrency slots are in-memory (R-19).
    # Binding all interfaces is required inside the container.
    uvicorn.run(application, host="0.0.0.0", port=8000, workers=1, log_config=None)  # noqa: S104
