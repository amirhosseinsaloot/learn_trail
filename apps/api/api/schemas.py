"""Request and response schemas for the HTTP boundary.

CLAUDE.md invariant #4 is about *model* output, but the same discipline applies
at the edge: nothing enters persistence without passing a Pydantic schema first.
These types are also what generates the OpenAPI document that
openapi-typescript turns into the frontend's types, so a field renamed here
becomes a TypeScript compile error there rather than a runtime surprise.

Read/write schemas are separate on purpose. A `ChatRead` carries server-owned
fields (`id`, `created_at`, `status`) that a client must never be able to set;
one shared model would either expose them as writable or need them all optional,
which makes every response's type a lie.

There is no user, owner, or author field anywhere in this module, and never will
be (CLAUDE.md invariant #1).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from database.models import ChangeSource, ChatStatus, DraftStatus, MessageRole

# Trimmed and non-empty, matching the `ck_chat_title_not_blank` CHECK constraint
# on the column. Validated here as well as in the database because a 422 naming
# the field is a better answer than a 500 from an IntegrityError — the database
# constraint is the backstop, not the interface.
ChatTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

# No max_length: `message.content` is TEXT precisely so a long paste is not
# rejected. Size limiting belongs to the Phase 4 safety pipeline's first stage
# ("size and format validation", docs/SPEC.md §8), where it can be a policy with
# a recorded decision rather than a magic number here.
MessageContent = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatCreate(BaseModel):
    """Body for creating a chat.

    The title is optional because a chat exists before it has one — it is
    generated from the conversation afterwards (docs/SPEC.md §6).
    """

    title: ChatTitle | None = None


class ChatRename(BaseModel):
    """Body for renaming a chat. The title is required — this endpoint's whole
    purpose is to set one, so an omitted field is a client error, not a clear."""

    title: ChatTitle


class MessageCreate(BaseModel):
    """Body for appending a message.

    Deliberately does **not** accept `role` or `sequence_number`. A client may
    only ever append its own turn, and the position in the transcript is the
    server's to assign — accepting either would let a caller forge an assistant
    message or reorder history.
    """

    content: MessageContent


class MessageRead(BaseModel):
    """One persisted turn."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    sequence_number: int
    created_at: datetime

    #: The trace that produced this turn (Phase 5), or `None` for a user turn and
    #: for anything answered before tracing existed. Read through `Message`'s own
    #: property, so the client never has to know a `model_run` table exists —
    #: what it needs is the handle that opens the trace.
    trace_id: str | None = None


class ChatRead(BaseModel):
    """A chat without its messages — the list view.

    `deleted_at` is exposed rather than hidden: a soft-deleted chat is restorable
    (docs/SPEC.md §6), so a client needs to be able to show it as deleted rather
    than have it silently vanish.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    status: ChatStatus
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class ChatDetail(ChatRead):
    """A chat with its full transcript — the resume view.

    This is what makes the Phase 1 exit criterion observable: stop the
    application, restart it, GET this, and the conversation is still there.
    """

    messages: list[MessageRead]


# --- summaries and learnings (Phase 3) ----------------------------------------


class SummaryContent(BaseModel):
    """The editable body of a draft or a Learning.

    A separate type from `ai_core.schemas.summary.LearningSummary` on purpose,
    even though the fields match. That one is what a *model* must produce and is
    validated on the way out of the model; this one is what a *person* may submit
    when they edit. Sharing the type would mean either loosening the model's
    contract or imposing generation-time rules on a human's edit — and a user who
    wants to delete every open question from their own Learning is entitled to.
    """

    model_config = ConfigDict(extra="forbid")

    title: ChatTitle
    overview: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    key_concepts: list[str] = Field(default_factory=list)
    distinctions: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    suggested_tags: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


class SummaryDraftRead(BaseModel):
    """A draft awaiting review. Model output, not knowledge."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    title: str
    structured_content: dict[str, Any]
    status: DraftStatus
    #: Which prompt version produced it (docs/SPEC.md §12).
    prompt_version: str
    created_at: datetime
    updated_at: datetime


class LearningRevisionRead(BaseModel):
    """One version of a Learning's content."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    revision_number: int
    structured_content: dict[str, Any]
    #: `model` for the approved draft, `human` for a later edit — the record of
    #: what was authored versus merely accepted.
    change_source: ChangeSource
    note: str | None
    created_at: datetime


class LearningRead(BaseModel):
    """An approved Learning, without its history — the library list view."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_chat_id: uuid.UUID | None
    title: str
    structured_content: dict[str, Any]
    approved_at: datetime
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class LearningDetail(LearningRead):
    """An approved Learning with its full revision history."""

    revisions: list[LearningRevisionRead]


class LearningEdit(BaseModel):
    """A human edit to an approved Learning. Writes a new revision."""

    model_config = ConfigDict(extra="forbid")

    content: SummaryContent
    #: Optional note about what changed. Free text — categories would be guessing.
    note: str | None = Field(default=None, max_length=500)


# --- retrieval (Phase 8) --------------------------------------------------------


class Citation(BaseModel):
    """One approved Learning that supplied context, and the passage it supplied.

    **This type is Phase 8's exit criterion.** The criterion asks that an answer
    identify *exactly* which approved Learning supplied its context, and a
    citation built from the retrieval record does that by construction: the
    `learning_id` is the row the chunk came from, not a number the model wrote in
    its prose and might have invented or omitted.

    `excerpt` is the chunk text verbatim, so a reader can check the answer against
    what the model was actually given rather than against the Learning as it
    stands today — those differ the moment the Learning is edited.
    """

    model_config = ConfigDict(from_attributes=True)

    learning_id: uuid.UUID
    learning_title: str
    chunk_index: int
    excerpt: str
    #: Fused rank score. Ordering within one response; meaningless across two.
    score: float
    #: `semantic`, `lexical`, or `both` — which half of the hybrid search found it.
    matched_by: str


class SearchResult(BaseModel):
    """What a plain search returns: passages, no generated answer."""

    query: str
    citations: list[Citation]


class AskRequest(BaseModel):
    """A question to answer from the approved library."""

    model_config = ConfigDict(extra="forbid")

    question: MessageContent
    #: How many chunks to retrieve. Bounded: more context is not free, and past a
    #: handful of passages the model starts averaging over them rather than using
    #: the best one.
    limit: int = Field(default=5, ge=1, le=20)


class AskResponse(BaseModel):
    """An answer grounded in approved Learnings, with its sources.

    `citations` is never inferred from the answer text. It is the list of chunks
    that were placed in the context, which is what "supplied the context" means —
    a Learning the model was given and chose not to lean on still supplied
    context, and pretending otherwise would require asking the model to introspect
    on its own reasoning.
    """

    question: str
    answer: str
    citations: list[Citation]
    #: True when nothing was retrieved. The answer then says so rather than being
    #: generated from the model's own knowledge — an ungrounded answer that looks
    #: like a grounded one is the failure this whole phase guards against.
    grounded: bool
    trace_id: str | None = None
