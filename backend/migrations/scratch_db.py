"""Create or drop a scratch database for `make migrate-check`.

Usage: python migrations/scratch_db.py <database-url> create|drop <name>

Connects to the `postgres` maintenance database on the same server as the
given URL. Only the round-trip check uses it; the application never does.
"""

import asyncio
import sys
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_ARGUMENTS = 3


async def run(url: str, action: str, name: str) -> None:
    parts = urlsplit(url)
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
            if action == "create":
                await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()


def main(argv: list[str]) -> int:
    if (
        len(argv) != EXPECTED_ARGUMENTS
        or argv[1] not in {"create", "drop"}
        or not argv[2].isidentifier()
    ):
        print(__doc__, file=sys.stderr)
        return 2
    asyncio.run(run(argv[0], argv[1], argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
