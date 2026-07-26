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
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from database.models import ChatStatus, MessageRole

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
