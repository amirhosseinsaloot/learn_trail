"""add evaluation tables

`evaluation_case` and `evaluation_result` (docs/SPEC.md §17, Phase 6).

The files under packages/evals/datasets/ remain the source of truth for cases;
this table is a registry that gives results something stable to point at. A case
row survives its file being deleted, because the results referencing it are still
history.

Both foreign keys on `evaluation_result` are ON DELETE SET NULL: a quality score
outlives the cost record and the case that explain it, and deleting either must
not silently rewrite the history of how the system performed.

Revision ID: 21fa67457e0f
Revises: 4f71f1779a49
Create Date: 2026-07-28 17:54:01.426293+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "21fa67457e0f"
down_revision: str | None = "4f71f1779a49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "evaluation_case",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.String(length=120), nullable=False),
        sa.Column("suite", sa.String(length=32), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "suite IN ('conversations', 'summaries', 'safety')",
            name=op.f("ck_evaluation_case_suite_is_known"),
        ),
        sa.CheckConstraint(
            "length(trim(case_id)) > 0", name=op.f("ck_evaluation_case_case_id_not_blank")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_case")),
        sa.UniqueConstraint("case_id", name=op.f("uq_evaluation_case_case_id")),
    )
    op.create_table(
        "evaluation_result",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_run_id", sa.Uuid(), nullable=True),
        sa.Column("evaluation_case_id", sa.Uuid(), nullable=True),
        sa.Column("evaluation_name", sa.String(length=100), nullable=False),
        sa.Column("evaluation_version", sa.String(length=100), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)",
            name=op.f("ck_evaluation_result_score_in_range"),
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_case_id"],
            ["evaluation_case.id"],
            name=op.f("fk_evaluation_result_evaluation_case_id_evaluation_case"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["model_run_id"],
            ["model_run.id"],
            name=op.f("fk_evaluation_result_model_run_id_model_run"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_result")),
    )
    op.create_index(
        "ix_evaluation_result_metric_recent",
        "evaluation_result",
        ["evaluation_name", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index("ix_evaluation_result_metric_recent", table_name="evaluation_result")
    op.drop_table("evaluation_result")
    op.drop_table("evaluation_case")
