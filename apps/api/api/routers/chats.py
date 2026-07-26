"""Chat and message endpoints (docs/SPEC.md §6).

Covers the persistence half of Phase 1: create a chat, list chats, resume one,
rename it, soft-delete and restore it, and append a user turn. **Answer
generation is deliberately not here** — docs/SPEC.md §6 lists "sending messages"
and "streaming answers" as separate endpoints, and the model call arrives with
the SSE endpoint later in Phase 1. That split is what makes this module
testable without a model, and it is why appending a message returns the
persisted user turn rather than an answer.

No authentication and no ownership checks anywhere: there is exactly one user
and no `user` table (CLAUDE.md invariant #1). A chat id is therefore a
capability, which is also why ids are UUIDs rather than sequential integers.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from api.schemas import (
    ChatCreate,
    ChatDetail,
    ChatRead,
    ChatRename,
    MessageCreate,
    MessageRead,
)
from database.models import Chat, ChatStatus, Message, MessageRole
from database.session import session

router = APIRouter(prefix="/chats", tags=["chats"])

# One alias for the session dependency so every handler's signature stays
# readable and there is a single place to change how sessions are provided.
Session = Annotated[AsyncSession, Depends(session)]


async def _load_chat(db: AsyncSession, chat_id: uuid.UUID) -> Chat:
    """Fetch a chat by id or raise 404.

    Soft-deleted chats are returned, not hidden: they are restorable, and an
    endpoint that 404s on them would make restore impossible. Endpoints that
    must refuse a deleted chat check `status` themselves, so the refusal reads
    as a 409 ("it's deleted") rather than a misleading 404 ("no such chat").
    """
    chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no chat with id {chat_id}")
    return chat


async def _commit_mutation(db: AsyncSession, chat: Chat) -> Chat:
    """Commit a change to a chat and re-read the column the database computed.

    The refresh is not optional. `Chat.updated_at` carries
    `onupdate=clock_timestamp()`, which the *database* evaluates — so once the
    UPDATE has run, the ORM knows its in-memory copy is stale and marks the
    attribute for reload. Serializing the chat then reads that attribute, and on
    an async session a reload triggered from synchronous attribute access raises
    `MissingGreenlet` — a 500 on the happy path, in every handler that mutates
    and then returns the row. `expire_on_commit=False` does not help: the staleness
    comes from the server-side default, not from the commit.

    Only `updated_at` is refreshed, deliberately: every other field is either
    unchanged or was set here in Python, so a full refresh would be a wider query
    for no new information.
    """
    await db.commit()
    await db.refresh(chat, attribute_names=["updated_at"])
    return chat


async def _next_sequence_number(db: AsyncSession, chat_id: uuid.UUID) -> int:
    """The next free position in a chat's transcript.

    Read-then-write, which is racy in principle. It is safe here for two
    reasons, in order of importance: the `uq_message_chat_id_sequence_number`
    constraint turns a lost race into a failed INSERT rather than two messages
    silently sharing a position, and this is a single-user application where two
    concurrent appends to one chat are not a real scenario. If concurrency ever
    becomes real, the fix is a database-side default or an advisory lock — not
    dropping the constraint that currently makes the race detectable.
    """
    query = select(func.max(Message.sequence_number)).where(Message.chat_id == chat_id)
    highest = (await db.execute(query)).scalar_one()
    return 0 if highest is None else highest + 1


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_chat(body: ChatCreate, db: Session) -> ChatDetail:
    """Create a chat, optionally titled."""
    # `messages=[]` is not decoration: passing the collection marks it *loaded*
    # on the new instance. Without it, `ChatDetail.model_validate` below reads an
    # unloaded relationship, which on an async session means lazy IO from
    # Pydantic's synchronous attribute access — `MissingGreenlet`, i.e. a 500 on
    # the happy path. A brand-new chat has no messages, so there is nothing to
    # fetch; this just tells SQLAlchemy that.
    chat = Chat(title=body.title, messages=[])
    db.add(chat)
    await db.commit()
    # ChatDetail rather than ChatRead so a client can render the (empty)
    # conversation straight from the create response, with no follow-up GET.
    return ChatDetail.model_validate(chat)


@router.get("")
async def list_chats(
    db: Session,
    include_deleted: Annotated[
        bool, Query(description="Include soft-deleted chats in the listing.")
    ] = False,
) -> list[ChatRead]:
    """List chats, most recently active first.

    Deleted chats are excluded by default — the common case is "show me my
    chats", and a soft-deleted one reappearing in that list would make deletion
    look broken. `ix_chat_active_recent` is the partial index built for exactly
    this query.
    """
    # `noload` because the relationship is `lazy="selectin"`: without it, listing
    # N chats issues a second query fetching every message of all N, to build a
    # response type (ChatRead) that has no messages field. Correct but pure
    # waste, and it grows with the transcript.
    query = select(Chat).options(noload(Chat.messages)).order_by(Chat.updated_at.desc())
    if not include_deleted:
        query = query.where(Chat.status == ChatStatus.ACTIVE)
    chats = (await db.execute(query)).scalars().all()
    return [ChatRead.model_validate(chat) for chat in chats]


@router.get("/{chat_id}")
async def get_chat(chat_id: uuid.UUID, db: Session) -> ChatDetail:
    """Resume a conversation: the chat plus its full transcript, in order.

    This endpoint *is* the Phase 1 exit criterion. Stop the application, restart
    it, call this, and the conversation is still there — because it was never in
    memory to begin with.
    """
    return ChatDetail.model_validate(await _load_chat(db, chat_id))


@router.patch("/{chat_id}")
async def rename_chat(chat_id: uuid.UUID, body: ChatRename, db: Session) -> ChatRead:
    """Rename a chat."""
    chat = await _load_chat(db, chat_id)
    chat.title = body.title
    return ChatRead.model_validate(await _commit_mutation(db, chat))


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: uuid.UUID, db: Session) -> None:
    """Soft-delete a chat. The row and its messages survive; only the two
    lifecycle columns change, so restore is possible (docs/SPEC.md §6).

    Idempotent, per HTTP's semantics for DELETE: deleting an
    already-deleted chat succeeds and does not move `deleted_at`, so the
    original deletion time is not overwritten by a retry.
    """
    chat = await _load_chat(db, chat_id)
    if chat.status is ChatStatus.DELETED:
        return
    chat.status = ChatStatus.DELETED
    # Set together, and only ever together: `ck_chat_status_matches_deleted_at`
    # rejects any commit where these two disagree.
    # Server-side clock, so the deletion time comes from the same source as
    # every other timestamp on the row rather than the application's clock.
    chat.deleted_at = func.clock_timestamp()
    await db.commit()


@router.post("/{chat_id}/restore")
async def restore_chat(chat_id: uuid.UUID, db: Session) -> ChatRead:
    """Undo a soft delete. Idempotent: restoring an active chat is a no-op."""
    chat = await _load_chat(db, chat_id)
    if chat.status is ChatStatus.DELETED:
        chat.status = ChatStatus.ACTIVE
        chat.deleted_at = None
        await _commit_mutation(db, chat)
    return ChatRead.model_validate(chat)


@router.post("/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
async def append_message(chat_id: uuid.UUID, body: MessageCreate, db: Session) -> MessageRead:
    """Append the user's turn to a chat.

    Returns only the persisted user message. The assistant's answer is a
    separate endpoint (docs/SPEC.md §6 lists "sending messages" and "streaming
    answers" separately) and arrives with the SSE endpoint later in Phase 1.

    `role` is fixed to `user` rather than taken from the body: a client may only
    append its own turn. Letting it choose would let it forge an assistant
    message, and from Phase 3 an approved Learning is derived from this
    transcript — so a forged turn would be a route to laundering model output
    past the human approval gate (CLAUDE.md invariant #5).
    """
    chat = await _load_chat(db, chat_id)
    if chat.status is ChatStatus.DELETED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"chat {chat_id} is deleted; restore it before adding messages",
        )

    message = Message(
        chat_id=chat.id,
        role=MessageRole.USER,
        content=body.content,
        sequence_number=await _next_sequence_number(db, chat.id),
    )
    db.add(message)

    # Appending a message is activity on the chat, and the chat list is ordered
    # by `updated_at` — but inserting a child row does not update the parent, so
    # the column's `onupdate` never fires on its own. Issued as an explicit
    # UPDATE so the timestamp comes from the database clock rather than the
    # application's.
    #
    # `clock_timestamp()` and not `now()`: `now()` is frozen for the transaction,
    # so a chat created and then messaged inside one transaction would keep its
    # original timestamp and silently fail to move to the top of the list.
    await db.execute(
        update(Chat).where(Chat.id == chat.id).values(updated_at=func.clock_timestamp())
    )

    await db.commit()
    return MessageRead.model_validate(message)
