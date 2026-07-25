"""Where the database URL comes from.

One rule: the URL is read from the ``DATABASE_URL`` environment variable, and
the fallback is a local-development default that matches the Postgres service
docker-compose.yml will define (Phase 0 task 8). Nothing here is a real
credential — the default user/password/database are all ``learntrail`` on a
throwaway local container, and production values arrive only via the
environment. No secret is ever committed to this repo.
"""

import os
from typing import Final

# Dialect note: `postgresql+psycopg` is psycopg 3 (see this package's
# pyproject.toml for why that driver). The bare `postgresql://` form would
# resolve to psycopg2, which is not a dependency, so the driver is pinned in
# the URL rather than left to SQLAlchemy's default.
#
# Contract for the docker-compose Postgres service (Phase 0 task 8): user
# `learntrail`, password `learntrail`, database `learntrail`, container port
# 5432 published on host port 5432. This default is the *host* view, used when
# running Alembic or the app straight from the repo venv. Containers reach
# Postgres by service name, so compose passes
# DATABASE_URL=postgresql+psycopg://learntrail:learntrail@postgres:5432/learntrail
# to the backend instead of relying on this default.
DEFAULT_DATABASE_URL: Final = "postgresql+psycopg://learntrail:learntrail@localhost:5432/learntrail"

DATABASE_URL_ENV_VAR: Final = "DATABASE_URL"


def database_url() -> str:
    """Return the SQLAlchemy URL for the LearnTrail database.

    Reads ``DATABASE_URL`` if set (and non-empty), else falls back to the local
    development default.
    """
    return os.environ.get(DATABASE_URL_ENV_VAR) or DEFAULT_DATABASE_URL
