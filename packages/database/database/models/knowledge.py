"""The knowledge aggregate: `summary_draft`, `learning`, `learning_revision`.

docs/SPEC.md §17, and the tables where CLAUDE.md invariant #5 becomes structural.

**Why a draft is a different table from a Learning, rather than a flag.**
A `summary_draft` is model output. A `learning` is knowledge the user accepted.
Collapsing them into one table with an `approved` boolean would mean every query
against the knowledge library carries the burden of remembering to filter — and
the one place that forgets silently promotes a draft. Two tables make the wrong
query return nothing rather than something dangerous.

`approved_at` on `learning` is `NOT NULL` for the same reason: a row exists only
because a human approved it, so there is no such thing as an unapproved
`learning` to represent.

**Structured content is JSONB, not columns.** `LearningSummary` is a validated
Pydantic shape (invariant #4) whose fields will change as the product does;
mirroring it into eight columns would mean a migration for every schema tweak and
would still not enforce the shape, because the validation that matters happens
before the write. What the database owns here is the *lifecycle* — draft versus
approved, and the revision history — which is exactly what the columns describe.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models.conversation import _enum_column


class DraftStatus(StrEnum):
    """Where a draft is in review (docs/SPEC.md §4).

    A draft leaves `PENDING` exactly once. `APPROVED` records that it became a
    Learning; `REJECTED` records that the user said no. Both are kept rather than
    deleted — "the model proposed this and I declined" is information, and Phase 6
    evaluates on precisely that signal.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ChangeSource(StrEnum):
    """Who caused a revision (docs/SPEC.md §17, `learning_revision.change_source`).

    The distinction the whole approval gate exists to preserve: `MODEL` means the
    text came from a generated draft the user approved, `HUMAN` means the user
    wrote or edited it themselves. Without this column the library would be a pile
    of text with no record of what was authored and what was merely accepted.
    """

    MODEL = "model"
    HUMAN = "human"


class SummaryDraft(Base):
    """A model-generated summary awaiting review.

    Never knowledge. It is what the user reads before deciding, and it is the only
    thing the summary graph is allowed to write.
    """

    __tablename__ = "summary_draft"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat.id", ondelete="CASCADE"), nullable=False
    )

    #: Denormalised out of `structured_content` so the review list can be rendered
    #: without parsing every draft's JSON.
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    #: A `LearningSummary`, already validated. The database stores it; it does not
    #: define it.
    structured_content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    status: Mapped[DraftStatus] = mapped_column(
        _enum_column(DraftStatus, "status_is_known"), default=DraftStatus.PENDING, nullable=False
    )

    #: e.g. `learning_summary@1`. docs/SPEC.md §12: every record says which prompt
    #: produced it, or the prompt library's versioning buys nothing.
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint("length(trim(prompt_version)) > 0", name="prompt_version_not_blank"),
        # At most one draft awaiting review per chat. Two would make "approve the
        # draft" ambiguous, and the review UI would have to invent a rule for
        # which one wins. Regenerating replaces the pending draft rather than
        # adding to it.
        Index(
            "uq_summary_draft_one_pending_per_chat",
            "chat_id",
            unique=True,
            postgresql_where=text(f"status = '{DraftStatus.PENDING.value}'"),
        ),
    )


class Learning(Base):
    """Knowledge the user approved. The durable half of the product.

    Soft-deleted like `chat`, because docs/SPEC.md §6 makes deletion restorable —
    and deleting something you spent a conversation earning should not be final on
    a misclick.
    """

    __tablename__ = "learning"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    #: Where it came from. `SET NULL` rather than `CASCADE`: deleting a
    #: conversation must not delete the knowledge derived from it. The Learning
    #: outlives the chat that produced it — that is the entire point of approving
    #: one.
    source_chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    structured_content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    #: NOT NULL: a row exists only because a human approved it. There is no
    #: unapproved Learning (CLAUDE.md invariant #5).
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    revisions: Mapped[list[LearningRevision]] = relationship(
        back_populates="learning",
        cascade="all, delete-orphan",
        order_by="LearningRevision.revision_number",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        Index(
            "ix_learning_live_recent",
            "updated_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class LearningRevision(Base):
    """One version of a Learning's content (docs/SPEC.md §17).

    Append-only. Every approval and every subsequent edit writes a row, so the
    library can answer "what did this say when I approved it, and what have I
    changed since" — which is the question that makes an edited Learning
    trustworthy rather than merely current.
    """

    __tablename__ = "learning_revision"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    learning_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning.id", ondelete="CASCADE"), nullable=False
    )

    #: 1 for the approved draft, incrementing per edit. Dense and per-learning,
    #: the same contract `message.sequence_number` has and for the same reason:
    #: timestamps tie, ordering must not.
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)

    structured_content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    change_source: Mapped[ChangeSource] = mapped_column(
        _enum_column(ChangeSource, "change_source_is_known"), nullable=False
    )

    #: Optional note about what changed and why. Free text — a structured reason
    #: would be guessing at categories nobody has needed yet.
    note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    learning: Mapped[Learning] = relationship(back_populates="revisions")

    __table_args__ = (
        UniqueConstraint("learning_id", "revision_number"),
        CheckConstraint("revision_number > 0", name="revision_number_positive"),
    )
