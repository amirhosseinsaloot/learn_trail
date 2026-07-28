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
from decimal import Decimal
from enum import StrEnum
from typing import Any, Final

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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

#: Width of the vectors `learning-embedding` produces (`text-embedding-3-small`).
#: Declared here because the column type needs it at import time, and duplicated
#: nowhere: `ai_core` imports this constant rather than restating 1536.
EMBEDDING_DIMENSIONS: Final = 1536


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

    #: The call that generated it (docs/SPEC.md §17). `SET NULL`: deleting the
    #: cost record must not delete the draft it explains.
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_run.id", ondelete="SET NULL")
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


class SafetyEvent(Base):
    """One safety decision about one interaction (docs/SPEC.md §8).

    Stored **separately from the content it judged**, which is the point of the
    table rather than a column on `message`: the message records what was said,
    this records what the system thought about it, and neither is rewritten to
    agree with the other. A blocked input has no message row at all, and its
    safety event is the only trace that the interaction happened — so this table
    is where "every model interaction has an explicit, testable safety path"
    becomes auditable after the fact.

    Append-only. A decision that can be edited later is not an audit record.
    """

    __tablename__ = "safety_event"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    #: Both nullable, and for different reasons. `chat_id` is null for a check
    #: that ran outside a conversation; `message_id` is null whenever the content
    #: was never persisted — which is every blocked interaction, and exactly the
    #: case worth keeping a record of.
    chat_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat.id", ondelete="CASCADE"))
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("message.id", ondelete="SET NULL")
    )

    #: `input` or `output` — the same policy can decide differently at each.
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Which check, e.g. `nemo_rails`, `pii_scan`, `size_limit`.
    policy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Which version of it. Without this the history is a claim about rules that
    #: may no longer exist.
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    #: One of docs/SPEC.md §8's six actions.
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Plural: one message can trip several concerns at once. JSONB rather than a
    #: join table because these are labels read as a set, never queried across.
    categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("stage IN ('input', 'output')", name="stage_is_known"),
        CheckConstraint(
            "action IN ('allow', 'allow_with_warning', 'redact', 'retry', 'block', "
            "'require_review')",
            name="action_is_known",
        ),
        CheckConstraint("severity >= 0", name="severity_non_negative"),
        # The audit query is "what happened recently, worst first".
        Index("ix_safety_event_recent", "created_at", "severity"),
    )


class ModelRun(Base):
    """One call to a model, and what it cost (docs/SPEC.md §17, Phase 5).

    **The join between the database and the traces.** `trace_id` is what turns "a
    poor answer" — a row someone is looking at — into a trace they can open, which
    is the Phase 5 exit criterion read from the storage side. Nullable, because a
    call made outside a trace must be recorded as untraced rather than given a
    fabricated id.

    **A row per call, not per answer.** A blocked answer still spent tokens, and a
    table that recorded only the answers people received would understate spend by
    exactly the amount spent on the ones they did not. `status` distinguishes the
    three endings, and `blocked` is deliberately not folded into `error`: one is
    the safety pipeline working.

    Referenced by `message` and `summary_draft` rather than referencing them:
    a run exists as soon as the model returns, and whether it becomes a message
    is decided afterwards.
    """

    __tablename__ = "model_run"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    #: 32 hex characters, or NULL. Indexed: "show me the run for this trace" is
    #: the query that makes a trace and a row navigable in both directions.
    trace_id: Mapped[str | None] = mapped_column(String(32), index=True)

    #: `chat.answer`, `summary.generate` — which of the system's reasons for
    #: spending money this was.
    operation: Mapped[str] = mapped_column(String(64), nullable=False)

    #: The role asked for, and the model that served it. Both, because both move
    #: independently — that indirection is the whole point of the alias.
    model_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(128), nullable=False)

    prompt_version: Mapped[str | None] = mapped_column(String(100))

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: USD. `Numeric`, never a float: money summed in binary floating point drifts,
    #: and this column exists to be summed. Nullable because an unpriced model is
    #: not a free one (ai_core/models/pricing.py) — 0 would be a lie that totals.
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("status IN ('ok', 'error', 'blocked')", name="status_is_known"),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0", name="token_counts_non_negative"
        ),
        CheckConstraint("latency_ms >= 0", name="latency_non_negative"),
        # The cost query is "what did the last week cost, worst first".
        Index("ix_model_run_recent", "created_at", "operation"),
    )


class EvaluationCase(Base):
    """A golden case, registered in the database (docs/SPEC.md §17, Phase 6).

    **The files under `packages/evals/datasets/` are the source of truth, not
    this table.** A case is reviewed in a pull request, versioned in git and
    diffable — none of which a row is. What the table adds is a stable identity
    to hang results off: `evaluation_result` needs something to point at, and
    pointing at a filename would break the first time a case is renamed.

    So this is a registry, synced from the files, and `case_id` is the join key
    rather than the primary key's meaning. A case that disappears from disk keeps
    its row, because the results that reference it are still history.
    """

    __tablename__ = "evaluation_case"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    #: The id from the file, e.g. `conv-001-index-vs-primary-key`. Unique: two
    #: cases sharing one would make every result about them ambiguous.
    case_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    #: `conversations`, `summaries`, `safety`.
    suite: Mapped[str] = mapped_column(String(32), nullable=False)

    #: The case as it was when synced, so a result can be read against the rubric
    #: that produced it rather than against whatever the file says today.
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

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
        CheckConstraint("suite IN ('conversations', 'summaries', 'safety')", name="suite_is_known"),
        CheckConstraint("length(trim(case_id)) > 0", name="case_id_not_blank"),
    )


class EvaluationResult(Base):
    """One metric's verdict on one model call (docs/SPEC.md §17, Phase 6).

    Attached to a `model_run`, which is what makes a score explicable: the run
    carries the trace, the alias, the provider model and the cost, so a score
    that dropped can be read against what actually changed. A result table with
    no link to the run would record *that* quality fell and nothing about why.

    `score` is nullable and `passed` is not. Some metrics are judgements without
    a number — "was this blocked, as the case required" is a yes or a no — and
    inventing a 1.0 for them would make an average across metrics meaningless.
    """

    __tablename__ = "evaluation_result"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    #: `SET NULL`, not `CASCADE`: a score outlives the cost record it explains,
    #: and deleting old runs must not silently rewrite quality history.
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_run.id", ondelete="SET NULL")
    )

    #: Which case produced it, when the result came from the golden set. NULL for
    #: a metric scored against live production output.
    evaluation_case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evaluation_case.id", ondelete="SET NULL")
    )

    #: e.g. `answer_relevance`, `summary_faithfulness`, `safety_policy_compliance`.
    evaluation_name: Mapped[str] = mapped_column(String(100), nullable=False)

    #: The metric's own version. A threshold that moved, or a judge prompt that
    #: changed, makes today's 0.8 incomparable with last month's — and without
    #: this column the history would look like a regression that never happened.
    evaluation_version: Mapped[str] = mapped_column(String(100), nullable=False)

    #: 0.0-1.0 where the metric produces one. NULL for pass/fail judgements.
    score: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    #: The judge's reasoning. The most useful column in the table when something
    #: fails, and the reason DeepEval's metrics are configured to produce one.
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 1)", name="score_in_range"),
        # The regression query is "how has this metric moved over time".
        Index("ix_evaluation_result_metric_recent", "evaluation_name", "created_at"),
    )


class LearningChunk(Base):
    """One retrievable piece of an approved Learning (docs/SPEC.md §17, Phase 8).

    **This table is what makes Phase 8's exit criterion answerable.** The
    criterion asks that an answer identify *exactly* which approved Learning
    supplied its context, and the only way to say that without guessing is for
    every retrievable unit to carry the id of the Learning it came from. A
    citation is then a fact about what was retrieved, not a claim the model made
    about its own reasoning — which it is in no position to know.

    **Derived data, and disposable.** A chunk is a projection of
    `learning.structured_content`: re-chunking or re-embedding rebuilds it
    exactly. Hence `CASCADE` — deleting a Learning must take its chunks with it,
    because a chunk that outlived its source would be citable context pointing at
    nothing.

    Only *approved* Learnings are chunked. Drafts are not knowledge (CLAUDE.md
    invariant #5), and indexing them would let unapproved model output supply the
    context for an answer — which is the approval gate defeated by the back door.
    """

    __tablename__ = "learning_chunk"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    learning_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning.id", ondelete="CASCADE"), nullable=False
    )

    #: Position within the Learning, from 0. Dense and ordered, so a retrieved
    #: chunk can be shown with its neighbours — a fragment quoted with no idea
    #: where it sat in the source is hard for a reader to trust.
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    #: The text that was embedded, verbatim. Stored rather than recomputed
    #: because the citation shows it: a user checking an answer needs to see the
    #: passage the model was actually given, not a fresh chunking of the current
    #: text that may have been edited since.
    content: Mapped[str] = mapped_column(Text, nullable=False)

    #: 1536 dimensions — `text-embedding-3-small` through the `learning-embedding`
    #: alias. The width is fixed in the column type, so changing to a model with
    #: a different one is a migration, which is the correct amount of friction
    #: for a change that invalidates every stored vector.
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)

    #: Which model produced the vector. Recorded because embeddings from two
    #: models are not comparable — a library indexed with one and queried with
    #: another returns confident nonsense, and without this column that failure
    #: is invisible. It is what lets a re-index know which rows are stale.
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    learning: Mapped[Learning] = relationship()

    __table_args__ = (
        UniqueConstraint("learning_id", "chunk_index"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        CheckConstraint("length(trim(content)) > 0", name="content_not_blank"),
        # Re-indexing one Learning deletes its chunks and writes new ones, so
        # this is the hot path for writes as well as the FK's natural index.
        Index("ix_learning_chunk_learning", "learning_id"),
        # Both search indexes are declared here as well as created in the
        # migration, and they have to be. `alembic check` compares the database
        # against *this metadata*: an index that exists only in the migration
        # looks like drift, and the next autogenerated revision helpfully offers
        # to drop it. Found by running `alembic check` immediately after applying
        # the migration, which is why that command is in the FAST lane.
        Index(
            "ix_learning_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
        Index(
            "ix_learning_chunk_content_fts",
            func.to_tsvector(text("'english'"), text("content")),
            postgresql_using="gin",
        ),
    )
