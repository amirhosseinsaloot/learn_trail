"""The conversation aggregate: `chat` and `message` (docs/SPEC.md §17).

This is the raw conversation memory layer of docs/ARCHITECTURE.md §6 — the
complete persisted chat. It is deliberately *not* knowledge: a chat holds
questions, wrong assumptions, model mistakes and dead ends (docs/SPEC.md §4).
Only an approved Learning is durable knowledge, and that table arrives in
Phase 3 behind a human approval gate.

Two field-level decisions worth stating once, since every later table will
follow them:

**Enums are `VARCHAR` + a named CHECK, not a Postgres `ENUM` type.** A native
enum type has to be altered with `ALTER TYPE ... ADD VALUE`, which is awkward
inside Alembic's transactional migrations and cannot be reversed at all — you
cannot drop a value. A CHECK constraint is rewritten by an ordinary migration.
The Python-side `StrEnum` is what application code uses, so the type safety is
kept where it is actually useful.

**`id` is a UUID generated in Python, not a serial.** The values show up in URLs
(`/chats/{id}/messages`), and a sequential integer both leaks how much the user
has written and invites guessing a neighbouring row. Generating client-side in
Python rather than with `gen_random_uuid()` means a row's identity is known
before the INSERT, which is what lets a request emit a `message_id` in a stream
before the transaction commits.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final

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
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base

if TYPE_CHECKING:
    from database.models.knowledge import ModelRun

# Length for every enum-backed VARCHAR column below. Wide enough for the values
# in use and any plausible sibling, narrow enough that a typo'd value is
# rejected by the CHECK rather than silently stored.
_ENUM_LEN: Final = 16


def _enum_column(python_enum: type[StrEnum], constraint_name: str) -> SqlEnum:
    """A `VARCHAR` + named CHECK column type for a Python `StrEnum`.

    Three non-default arguments, each load-bearing:

    - ``native_enum=False`` — store as VARCHAR with a CHECK rather than creating
      a Postgres ENUM type. A native enum can only be extended with
      ``ALTER TYPE ... ADD VALUE`` (awkward inside Alembic's transactional
      migrations) and a value can never be removed. A CHECK is rewritten by an
      ordinary migration.
    - ``values_callable`` — SQLAlchemy stores enum **names** by default, so
      without this the database would hold ``'USER'`` while every string literal
      in the app, in SQL consoles and in this file's CHECK constraints says
      ``'user'``.
    - ``create_constraint=True`` — the CHECK is *not* emitted by default in
      SQLAlchemy 2.0. Without it the column is an unconstrained VARCHAR and any
      typo persists happily.

    Using this instead of a bare ``String`` is what makes the ``Mapped[...]``
    annotation true: a plain String column returns ``str`` on load, so the
    annotation would claim an enum that only ever appears on the write path —
    and mypy would allow enum-only attribute access that fails at runtime.
    """
    return SqlEnum(
        python_enum,
        native_enum=False,
        length=_ENUM_LEN,
        values_callable=lambda enum: [member.value for member in enum],
        # Interpolated into the naming convention's `ck` template, so this
        # becomes e.g. ck_message_role_is_known.
        name=constraint_name,
        create_constraint=True,
        # Reject unknown strings in Python too, not only at the database.
        validate_strings=True,
    )


class ChatStatus(StrEnum):
    """Lifecycle of a chat.

    Kept in lockstep with ``Chat.deleted_at`` by a CHECK constraint: a chat is
    `deleted` exactly when it carries a deletion timestamp. Two columns for one
    fact is redundant, and docs/SPEC.md §17 lists both, so the redundancy is
    made unbreakable at the database level instead of trusted to application
    code. `status` is what queries filter on; `deleted_at` is when it happened,
    which is what makes restore possible.
    """

    ACTIVE = "active"
    DELETED = "deleted"


class MessageRole(StrEnum):
    """Who produced a message.

    `system` is stored rather than assembled on the fly so a conversation can be
    replayed exactly as it was sent — a prompt change must not retroactively
    rewrite what the model actually saw.
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Chat(Base):
    """One conversation thread.

    Soft-deleted, never hard-deleted by the application: docs/SPEC.md §6 lists
    "Deleting and restoring content" as a first-class endpoint, so the row has to
    survive its own deletion.
    """

    __tablename__ = "chat"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Nullable on purpose: a chat is created before its first message, and the
    # title is generated from the conversation afterwards (docs/SPEC.md §6,
    # "Generating titles"). NULL means "not titled yet", which is a different
    # thing from an empty string — hence the CHECK forbidding blank titles.
    title: Mapped[str | None] = mapped_column(String(200))

    status: Mapped[ChatStatus] = mapped_column(
        _enum_column(ChatStatus, "status_is_known"), default=ChatStatus.ACTIVE, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Maintained by the application, not by a database trigger: SQLAlchemy's
    # `onupdate` only fires for ORM/Core updates, and a hand-written migration
    # that bulk-updates rows will not touch it. That is the intended behaviour —
    # a migration is not a user edit.
    #
    # `clock_timestamp()`, NOT `now()`. In Postgres `now()` is an alias for
    # `transaction_timestamp()` and is frozen for the whole transaction, so two
    # updates in one transaction — or an update in the same transaction that
    # inserted the row — leave this column unchanged. Since this is the column
    # the chat list is ordered by, that failure mode is silent: the list simply
    # does not reorder. `clock_timestamp()` advances per call.
    #
    # `onupdate` is ORM-side, not DDL, so it does not appear in a migration —
    # only `server_default` does. Changing it needs no revision.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[Message]] = relationship(
        back_populates="chat",
        # A chat is only ever hard-deleted in tests or by hand; when it happens,
        # its messages must not outlive it. `delete-orphan` so detaching a
        # message from its chat deletes it rather than leaving a NULL chat_id,
        # which the NOT NULL column would reject anyway.
        cascade="all, delete-orphan",
        # Ordering lives here so `chat.messages` is never accidentally read in
        # insertion-order-by-luck. It matches the unique constraint below.
        order_by="Message.sequence_number",
        # Messages are read as a whole conversation or not at all, so the lazy
        # default's N+1 risk is not worth carrying.
        lazy="selectin",
    )

    __table_args__ = (
        # Every CheckConstraint needs an explicit `name=`: the naming convention
        # on Base interpolates %(constraint_name)s for `ck`, and an unnamed
        # check makes DDL compilation fail with a confusing InvalidRequestError.
        CheckConstraint(
            "(status = 'deleted') = (deleted_at IS NOT NULL)",
            name="status_matches_deleted_at",
        ),
        # (`ck_chat_status_is_known` is generated by the column's Enum type.)
        # A titled chat has a real title. NULL is allowed (untitled); blank is
        # not, because it renders as an invisible row in the chat list.
        CheckConstraint("title IS NULL OR length(trim(title)) > 0", name="title_not_blank"),
        # The chat list is "most recently active first, excluding deleted".
        # Partial, so the index holds only the rows that list actually scans.
        #
        # The predicate is `text()`, not `status == ...`: inside a class body
        # `status` is still a MappedColumn, not the InstrumentedAttribute it
        # becomes after mapper configuration, so comparing it here does not
        # reliably produce a SQL expression.
        Index(
            "ix_chat_active_recent",
            "updated_at",
            postgresql_where=text(f"status = '{ChatStatus.ACTIVE.value}'"),
        ),
    )


class Message(Base):
    """One turn in a conversation.

    Append-only: messages are never edited or deleted in place. Re-asking is a
    new message, which is what makes a chat a faithful record of what happened.
    """

    __tablename__ = "message"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[MessageRole] = mapped_column(
        _enum_column(MessageRole, "role_is_known"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Dense per-chat ordering, assigned by the application. A timestamp is not
    # enough: two messages written in the same transaction can share a
    # `created_at` to microsecond precision, leaving the transcript order
    # ambiguous — and the order of a conversation is not a detail.
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    #: The model call that produced it, for an assistant turn (docs/SPEC.md §17).
    #: Always NULL on a user turn — the user's question cost nothing. `SET NULL`
    #: rather than `CASCADE`: deleting the cost record must not delete the answer.
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_run.id", ondelete="SET NULL")
    )

    #: Eager, and it has to be. A transcript is serialised straight out of the
    #: session, and a lazy load triggered by attribute access during that
    #: serialisation raises `MissingGreenlet` on an async session — the same trap
    #: `_commit_mutation` documents in the API layer.
    #:
    #: The class is named as a string because `ModelRun` lives in the knowledge
    #: module, which imports this one. SQLAlchemy resolves it through the registry,
    #: so the import cycle never has to exist.
    model_run: Mapped[ModelRun | None] = relationship(lazy="selectin")

    @property
    def trace_id(self) -> str | None:
        """The trace that produced this turn, if it was produced by a model.

        Exposed on the message rather than making every client join: "show me why
        this answer was poor" is one click from a transcript, and a link that
        needed a second request would not be one.
        """
        return self.model_run.trace_id if self.model_run is not None else None

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chat: Mapped[Chat] = relationship(back_populates="messages")

    __table_args__ = (
        # The ordering contract, enforced rather than assumed. This is also what
        # makes concurrent appends to one chat fail loudly instead of silently
        # interleaving into an ambiguous transcript.
        UniqueConstraint("chat_id", "sequence_number"),
        # (`ck_message_role_is_known` is generated by the column's Enum type.)
        CheckConstraint("sequence_number >= 0", name="sequence_number_non_negative"),
        CheckConstraint("length(content) > 0", name="content_not_empty"),
    )


# Deliberately absent: `message.model_run_id`, which docs/SPEC.md §17 lists.
# `model_run` is the cost/latency/token record that arrives with observability in
# Phase 5, and a nullable column pointing at a table that does not exist is
# either a lie (no FK) or unmigratable (FK to nothing). It joins `message` in the
# same migration that creates `model_run`.
