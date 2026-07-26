"""Alembic migration environment for LearnTrail.

Two differences from Alembic's stock template, both deliberate:

1. The database URL is **not** read from alembic.ini. It comes from
   ``DATABASE_URL`` (with a local default) through
   :func:`database.config.database_url`, so no credential lives in a committed
   file and the migration runner and the app agree on one source of truth.
2. The engine is built explicitly with :func:`sqlalchemy.create_engine` instead
   of ``engine_from_config``, since there is no ``sqlalchemy.*`` config section
   to read. Migrations run on a sync connection — psycopg 3 serves both this
   sync dialect and the app's async one (see this package's pyproject.toml).

``target_metadata`` is an empty declarative base's metadata in Phase 0: there
are no models yet, so autogenerate has nothing to diff (docs/SPEC.md §15).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

# Imported for its side effect: defining a model class registers its table on
# Base.metadata, and autogenerate diffs *metadata* against the live schema. With
# this import missing, `alembic revision --autogenerate` sees empty metadata and
# cheerfully generates a migration that DROPS every table. It is a plain
# `import database.models` rather than importing names, because nothing in this
# file uses the classes — only their registration matters.
import database.models  # noqa: F401
from database.base import Base
from database.config import database_url

# The Config object for the alembic.ini (or -c) file currently in use.
config = context.config

# Wire up Python logging exactly as the .ini describes, when invoked with one.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate's source of truth for "what the schema should look like".
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database (``--sql``).

    Calls are rendered with literal values inlined, since there is no DBAPI
    connection available to bind parameters.
    """
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    """Configure the migration context against a live connection and run it."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Catch column type / server-default drift between models and the live
        # schema, which Alembic ignores by default.
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and run migrations in a transaction.

    ``NullPool``: a migration process is short-lived and uses one connection,
    so pooling only risks holding a connection open after the run finishes.
    """
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            _run_migrations(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
