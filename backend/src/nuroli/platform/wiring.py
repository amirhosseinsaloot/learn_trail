"""Composition root (IMPLEMENTATION.md section 2.3).

Builds the infrastructure objects every request depends on. Feature tickets
extend ``Dependencies`` with repositories, adapters, and use-case factories
here, and the platform dependency providers hand them to routers; routers
never construct infrastructure themselves.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from nuroli.platform.db import create_engine, create_session_factory
from nuroli.platform.settings import Settings


@dataclass(frozen=True)
class Dependencies:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


def build(settings: Settings) -> Dependencies:
    engine = create_engine(settings)
    return Dependencies(engine=engine, session_factory=create_session_factory(engine))
