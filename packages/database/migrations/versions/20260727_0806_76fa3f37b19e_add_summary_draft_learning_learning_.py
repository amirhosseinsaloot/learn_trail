"""add summary_draft, learning, learning_revision

The knowledge aggregate (docs/SPEC.md §17), and the schema half of CLAUDE.md
invariant #5. `summary_draft` and `learning` are separate tables rather than one
table with an `approved` flag, so a query that forgets to filter returns nothing
rather than promoting model output. `learning.approved_at` is NOT NULL because a
row exists only because a human approved it.

`learning.source_chat_id` is ON DELETE SET NULL, not CASCADE: deleting a
conversation must not delete the knowledge derived from it.

Revision ID: 76fa3f37b19e
Revises: 6ab72a617d4e
Create Date: 2026-07-27 08:06:11.315914+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "76fa3f37b19e"
down_revision: str | None = "6ab72a617d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "learning",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_chat_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("structured_content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(trim(title)) > 0", name=op.f("ck_learning_title_not_blank")),
        sa.ForeignKeyConstraint(
            ["source_chat_id"],
            ["chat.id"],
            name=op.f("fk_learning_source_chat_id_chat"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learning")),
    )
    op.create_index(
        "ix_learning_live_recent",
        "learning",
        ["updated_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "summary_draft",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("structured_content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                name="status_is_known",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
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
            "length(trim(prompt_version)) > 0",
            name=op.f("ck_summary_draft_prompt_version_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0", name=op.f("ck_summary_draft_title_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"], ["chat.id"], name=op.f("fk_summary_draft_chat_id_chat"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_summary_draft")),
    )
    op.create_index(
        "uq_summary_draft_one_pending_per_chat",
        "summary_draft",
        ["chat_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "learning_revision",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("learning_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("structured_content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "change_source",
            sa.Enum(
                "model",
                "human",
                name="change_source_is_known",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision_number > 0", name=op.f("ck_learning_revision_revision_number_positive")
        ),
        sa.ForeignKeyConstraint(
            ["learning_id"],
            ["learning.id"],
            name=op.f("fk_learning_revision_learning_id_learning"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learning_revision")),
        sa.UniqueConstraint(
            "learning_id",
            "revision_number",
            name=op.f("uq_learning_revision_learning_id_revision_number"),
        ),
    )
    op.drop_index(op.f("checkpoint_blobs_thread_id_idx"), table_name="checkpoint_blobs")
    op.drop_table("checkpoint_blobs")
    op.drop_table("checkpoint_migrations")
    op.drop_index(op.f("checkpoints_thread_id_idx"), table_name="checkpoints")
    op.drop_table("checkpoints")
    op.drop_index(op.f("checkpoint_writes_thread_id_idx"), table_name="checkpoint_writes")
    op.drop_table("checkpoint_writes")


def downgrade() -> None:
    """Revert this revision."""
    op.create_table(
        "checkpoint_writes",
        sa.Column("thread_id", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column(
            "checkpoint_ns",
            sa.TEXT(),
            server_default=sa.text("''::text"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("checkpoint_id", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("task_id", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("idx", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("channel", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("type", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column("blob", postgresql.BYTEA(), autoincrement=False, nullable=False),
        sa.Column(
            "task_path",
            sa.TEXT(),
            server_default=sa.text("''::text"),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
            "task_id",
            "idx",
            name=op.f("checkpoint_writes_pkey"),
        ),
    )
    op.create_index(
        op.f("checkpoint_writes_thread_id_idx"), "checkpoint_writes", ["thread_id"], unique=False
    )
    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column(
            "checkpoint_ns",
            sa.TEXT(),
            server_default=sa.text("''::text"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("checkpoint_id", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("parent_checkpoint_id", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column("type", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column(
            "checkpoint",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "thread_id", "checkpoint_ns", "checkpoint_id", name=op.f("checkpoints_pkey")
        ),
    )
    op.create_index(op.f("checkpoints_thread_id_idx"), "checkpoints", ["thread_id"], unique=False)
    op.create_table(
        "checkpoint_migrations",
        sa.Column("v", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("v", name=op.f("checkpoint_migrations_pkey")),
    )
    op.create_table(
        "checkpoint_blobs",
        sa.Column("thread_id", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column(
            "checkpoint_ns",
            sa.TEXT(),
            server_default=sa.text("''::text"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("channel", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("version", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("type", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("blob", postgresql.BYTEA(), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint(
            "thread_id", "checkpoint_ns", "channel", "version", name=op.f("checkpoint_blobs_pkey")
        ),
    )
    op.create_index(
        op.f("checkpoint_blobs_thread_id_idx"), "checkpoint_blobs", ["thread_id"], unique=False
    )
    op.drop_table("learning_revision")
    op.drop_index(
        "uq_summary_draft_one_pending_per_chat",
        table_name="summary_draft",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_table("summary_draft")
    op.drop_index(
        "ix_learning_live_recent",
        table_name="learning",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("learning")
