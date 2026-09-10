"""Alembic environment.

Online runs use the connection the ``migrate`` command provides through
``config.attributes["connection"]``; the Alembic CLI (``make migrate``,
``make migration``, ``make migrate-check``) builds an async engine from the
application settings instead. Feature tickets import their
``infrastructure.models`` modules below so autogenerate sees every table.
"""

import asyncio

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from nuroli.platform.db import metadata
from nuroli.platform.settings import load_settings

config = context.config
target_metadata = metadata


def run_migrations_offline() -> None:
    context.configure(
        url=load_settings().database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_with(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_from_settings() -> None:
    engine = create_async_engine(
        load_settings().database_url.get_secret_value(), poolclass=NullPool
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations_with)
            await connection.commit()
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        run_migrations_with(connection)
    else:
        asyncio.run(run_migrations_from_settings())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
