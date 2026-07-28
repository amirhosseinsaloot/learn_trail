"""add safety_event

The audit trail for docs/SPEC.md §8. Deliberately not a column on `message`:
a blocked interaction has no message row, and its safety event is the only
record that it happened at all.

`message_id` is ON DELETE SET NULL rather than CASCADE — deleting a message must
not erase the record of the decision made about it.

Revision ID: 76b6e416988a
Revises: 76fa3f37b19e
Create Date: 2026-07-28 08:02:53.654238+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "76b6e416988a"
down_revision: str | None = "76fa3f37b19e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "safety_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("policy_name", sa.String(length=100), nullable=False),
        sa.Column("policy_version", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('allow', 'allow_with_warning', 'redact', 'retry', 'block', "
            "'require_review')",
            name=op.f("ck_safety_event_action_is_known"),
        ),
        sa.CheckConstraint(
            "stage IN ('input', 'output')", name=op.f("ck_safety_event_stage_is_known")
        ),
        sa.CheckConstraint("severity >= 0", name=op.f("ck_safety_event_severity_non_negative")),
        sa.ForeignKeyConstraint(
            ["chat_id"], ["chat.id"], name=op.f("fk_safety_event_chat_id_chat"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["message.id"],
            name=op.f("fk_safety_event_message_id_message"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_safety_event")),
    )
    op.create_index(
        "ix_safety_event_recent", "safety_event", ["created_at", "severity"], unique=False
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index("ix_safety_event_recent", table_name="safety_event")
    op.drop_table("safety_event")
