"""Operator commands (ARCHITECTURE.md section 10).

``migrate`` runs ``alembic upgrade head`` under the PostgreSQL advisory lock
7245, so two API containers starting together apply migrations once and in
order; the container entrypoint runs it before serving. Later tickets add
``check-model``, ``reset-password``, and ``delete-user``.

Usage: ``python -m nuroli.platform.cli migrate``
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text

from nuroli.platform.db import create_engine, current_revision
from nuroli.platform.logging import configure_logging
from nuroli.platform.settings import Settings, SettingsError, load_settings

MIGRATION_LOCK_ID = 7245
BACKEND_DIR = Path(__file__).resolve().parents[3]

log = logging.getLogger("nuroli.migrate")


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def script_head() -> str:
    """Newest revision in the migrations directory; ``none`` when there are no migrations."""
    return ScriptDirectory.from_config(alembic_config()).get_current_head() or "none"


def _upgrade_with(connection: Connection) -> None:
    config = alembic_config()
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def migrate(settings: Settings) -> str:
    """Apply migrations under the advisory lock; return the revision the database is at."""
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT pg_advisory_lock(:id)"), {"id": MIGRATION_LOCK_ID}
            )
            log.info("migration lock acquired", extra={"lock_id": MIGRATION_LOCK_ID})
            try:
                await connection.run_sync(_upgrade_with)
                await connection.commit()
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:id)"), {"id": MIGRATION_LOCK_ID}
                )
                log.info("migration lock released", extra={"lock_id": MIGRATION_LOCK_ID})
        revision = await current_revision(engine)
    finally:
        await engine.dispose()
    log.info("migrations applied", extra={"revision": revision})
    return revision or "none"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nuroli", description="Nuroli operator commands")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("migrate", help="apply database migrations under an advisory lock")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.command == "migrate":
        configure_logging(settings)
        revision = asyncio.run(migrate(settings))
        print(f"migrations applied; database at revision {revision}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
