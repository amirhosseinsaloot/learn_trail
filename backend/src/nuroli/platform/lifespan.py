"""Startup and shutdown (ARCHITECTURE.md section 19).

Startup wires the composition root onto ``app.state`` and records the Alembic
head so ``/ready`` can compare it with the database. Shutdown disposes the
engine. Timers and the stale-stream reconciliation arrive in later tickets.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from nuroli.platform import wiring
from nuroli.platform.cli import script_head
from nuroli.platform.settings import Settings

log = logging.getLogger("nuroli")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    dependencies = wiring.build(settings)
    app.state.engine = dependencies.engine
    app.state.session_factory = dependencies.session_factory
    app.state.migration_head = script_head()
    log.info("startup complete", extra={"migration_head": app.state.migration_head})
    try:
        yield
    finally:
        await dependencies.engine.dispose()
        log.info("shutdown complete")
