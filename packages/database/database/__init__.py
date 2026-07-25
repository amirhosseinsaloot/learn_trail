"""LearnTrail persistence layer.

Bottom layer of the docs/SPEC.md §16 layout: `database` owns SQLAlchemy metadata
and the Alembic migration environment, and imports no `api`, `ai_core`, or
`evals` code (docs/CODE_QUALITY.md, import-linter contracts 1 and 3).

Phase 0 ships the migration environment only — no models, no tables, no
revisions. Phase 1 adds the first two tables, `chat` and `message`
(docs/SPEC.md §6, §15, §17).
"""

from database.base import Base
from database.config import database_url

__all__ = ["Base", "database_url"]
