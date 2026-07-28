"""add model_run

The cost and latency record for every model call (docs/SPEC.md §17), plus the
`model_run_id` back-references on `message` and `summary_draft`.

`estimated_cost` is NUMERIC, not a float: this column exists to be summed, and
money summed in binary floating point drifts. It is nullable because an unpriced
model is not a free one — see ai_core/models/pricing.py.

Both foreign keys are ON DELETE SET NULL. Deleting the record of what an answer
cost must not delete the answer.

Revision ID: 4f71f1779a49
Revises: 76b6e416988a
Create Date: 2026-07-28 16:15:16.081999+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f71f1779a49"
down_revision: str | None = "76b6e416988a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "model_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("model_alias", sa.String(length=64), nullable=False),
        sa.Column("provider_model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'blocked')", name=op.f("ck_model_run_status_is_known")
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0",
            name=op.f("ck_model_run_token_counts_non_negative"),
        ),
        sa.CheckConstraint("latency_ms >= 0", name=op.f("ck_model_run_latency_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_run")),
    )
    op.create_index("ix_model_run_recent", "model_run", ["created_at", "operation"], unique=False)
    op.create_index(op.f("ix_model_run_trace_id"), "model_run", ["trace_id"], unique=False)
    op.add_column("message", sa.Column("model_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_message_model_run_id_model_run"),
        "message",
        "model_run",
        ["model_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("summary_draft", sa.Column("model_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_summary_draft_model_run_id_model_run"),
        "summary_draft",
        "model_run",
        ["model_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_constraint(
        op.f("fk_summary_draft_model_run_id_model_run"), "summary_draft", type_="foreignkey"
    )
    op.drop_column("summary_draft", "model_run_id")
    op.drop_constraint(op.f("fk_message_model_run_id_model_run"), "message", type_="foreignkey")
    op.drop_column("message", "model_run_id")
    op.drop_index(op.f("ix_model_run_trace_id"), table_name="model_run")
    op.drop_index("ix_model_run_recent", table_name="model_run")
    op.drop_table("model_run")
