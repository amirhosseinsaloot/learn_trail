"""citext extension for case-insensitive email uniqueness (ARCHITECTURE.md section 10).

Revision ID: 0001
Revises: None
Create Date: 2026-09-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Requires the application role to own the database; the Compose stack's
    # POSTGRES_USER does. Documented for external databases in the README (NU-039).
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS citext")
