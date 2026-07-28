"""Chat and message endpoints (docs/SPEC.md §6).

The whole Phase 1 chat surface: create a chat, list chats, resume one, rename it,
soft-delete and restore it, append a user turn, and stream an answer.

Appending a message and answering are separate endpoints, as docs/SPEC.md §6
lists them. That is not ceremony: it keeps every persistence path testable with
no model and no API key, and it means a failed model call cannot lose a question
the user already asked.

No authentication and no ownership checks anywhere: there is exactly one user
and no `user` table (CLAUDE.md invariant #1). A chat id is therefore a
capability, which is also why ids are UUIDs rather than sequential integers.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from ai_core import ChatTurn, CompletionResponse, GatewayError, ModelAlias
from ai_core.graphs.chat import PERSIST_KEY, RECORD_SAFETY_KEY, ChatState, GraphError
from ai_core.graphs.messages import context_to_langchain
from ai_core.safety.decisions import SafetyOutcome, SafetyStage
from ai_core.telemetry import Attr, activate, current_trace_id, span, start_span
from ai_core.telemetry.spans import CHAT_REQUEST, LOAD_CONVERSATION
from api import sse
from api.graph import chat_graph
from api.schemas import (
    ChatCreate,
    ChatDetail,
    ChatRead,
    ChatRename,
    MessageCreate,
    MessageRead,
)
from database.models import Chat, ChatStatus, Message, MessageRole, SafetyEvent
from database.session import session

router = APIRouter(prefix="/chats", tags=["chats"])

# One alias for the session dependency so every handler's signature stays
# readable and there is a single place to change how sessions are provided.
Session = Annotated[AsyncSession, Depends(session)]

# The compiled chat graph, from app.state (api/graph.py). A dependency rather
# than a module import so a test can substitute one, and so the handler cannot
# accidentally build its own — compiling per request would open a checkpointer
# connection pool per request.
ChatGraph = Annotated[Any, Depends(chat_graph)]


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


def _working_context(chat: Chat) -> list[ChatTurn]:
    """Assemble what the model actually sees for this request.

    The *working context* of docs/ARCHITECTURE.md §6 — deliberately a different
    thing from the transcript. Phase 1 uses the simplest strategy docs/SPEC.md
    §14 lists, full history, which is correct for short chats and will stop being
    correct: the alternatives (recent-window, previous-summary-plus-recent,
    relevance-selected) are exactly what `build_context` becomes as a graph node
    in Phase 2.

    Isolated in one function now so that change is local. Note it maps rows onto
    `ChatTurn` rather than passing them through: `ai_core` never sees a database
    model, which is what keeps the working context an assembled thing rather than
    "the transcript, but passed along".
    """
    return [ChatTurn(role=message.role.value, content=message.content) for message in chat.messages]


@router.post("/{chat_id}/answer")
async def stream_answer(chat_id: uuid.UUID, db: Session, graph: ChatGraph) -> StreamingResponse:
    """Stream the assistant's answer to the conversation so far, then persist it.

    The answer half of "send a message" — docs/SPEC.md §6 lists streaming answers
    as its own endpoint, and this is it. `POST /chats/{id}/messages` appends the
    question; this produces the reply.

    **Phase 2 replaced the direct model call here with a graph invocation.** What
    this handler now does is translate: HTTP in, graph state out, graph events
    back to SSE. The five steps of the workflow — validate, build context, choose
    model, generate, persist — live in `ai_core.graphs.chat`, where each is a
    named node the checkpointer records.

    The HTTP-level checks below survive that move on purpose. They are not a
    duplicate of the graph's `validate_input`: these exist to produce *status
    codes*, and a status code can only be sent before the stream opens. The graph
    node guards the graph's own preconditions for any caller, including ones that
    never came through HTTP.

    Consume it with `fetch` + a ReadableStream, not `EventSource`: EventSource
    only issues GET requests, and this endpoint is a POST because it creates a
    message.
    """
    # Started here and ended inside `events()` below, because the operation this
    # span measures does not fit inside this function: the handler returns a
    # `StreamingResponse` and the graph only runs afterwards, as the body is
    # consumed. A `with` block here would close the span before the model call
    # it is supposed to contain had begun.
    request_span = start_span(CHAT_REQUEST, {Attr.CHAT_ID: str(chat_id)})

    try:
        with activate(request_span), span(LOAD_CONVERSATION):
            chat = await _load_chat(db, chat_id)
    except BaseException:
        # Including HTTPException — a 404 for an unknown chat is a fact about
        # this request, and a span left open would never be exported at all.
        request_span.end()
        raise

    if chat.status is ChatStatus.DELETED:
        request_span.end()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"chat {chat_id} is deleted; restore it before answering"
        )
    if not chat.messages:
        request_span.end()
        raise HTTPException(status.HTTP_409_CONFLICT, f"chat {chat_id} has no messages to answer")
    if chat.messages[-1].role is not MessageRole.USER:
        # Answering an assistant turn would produce the model replying to itself.
        request_span.end()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "the last message is not a question; append a user message first",
        )

    context = _working_context(chat)
    next_position = await _next_sequence_number(db, chat.id)

    # The graph's `persist` node calls this. Injecting it rather than letting
    # `ai_core` import `database` keeps every node a function of its inputs, so
    # the whole workflow can be exercised with no Postgres — and it keeps the
    # request's session, which the graph knows nothing about, in the layer that
    # owns it.
    async def persist_answer(answer: CompletionResponse) -> str:
        message = Message(
            chat_id=chat.id,
            role=MessageRole.ASSISTANT,
            content=answer.text,
            sequence_number=next_position,
        )
        db.add(message)
        await db.flush()

        # The output check ran *before* this message existed, so its events were
        # written with a null `message_id`. Now that the answer has a row, point
        # them at it: an auditor asking "what was decided about this message"
        # should not have to reconstruct the link from timestamps.
        if output_event_ids:
            await db.execute(
                update(SafetyEvent)
                .where(SafetyEvent.id.in_(output_event_ids))
                .values(message_id=message.id)
            )

        await db.execute(
            update(Chat).where(Chat.id == chat.id).values(updated_at=func.clock_timestamp())
        )
        await db.commit()
        return str(message.id)

    #: Ids of this request's output-stage events, so `persist_answer` can attach
    #: them to the message once it has one. Empty for a blocked answer, which is
    #: the case where the event stands alone as the only record.
    output_event_ids: list[uuid.UUID] = []

    async def record_safety(outcome: SafetyOutcome) -> None:
        """Write one row per check, allow or not.

        Committed as soon as the decision is made, not batched to the end of the
        request: a run that fails afterwards — a dead stream, a gateway error —
        must still leave behind the record that it was checked. An audit trail
        that only survives success is not one.
        """
        rows = [
            SafetyEvent(
                chat_id=chat.id,
                stage=decision.stage.value,
                policy_name=decision.policy_name,
                policy_version=decision.policy_version,
                action=decision.action.value,
                severity=decision.severity,
                # Categories only. `find_pii` deliberately returns no matched
                # values, and an audit row quoting the credential it found would
                # have copied the secret into a second place.
                categories=list(decision.categories),
                explanation=decision.explanation,
            )
            for decision in outcome.decisions
        ]
        db.add_all(rows)
        await db.commit()
        if outcome.stage is SafetyStage.OUTPUT:
            output_event_ids.extend(row.id for row in rows)

    async def events() -> AsyncIterator[str]:
        with activate(request_span, end=True):
            async for frame in _answer_events():
                yield frame

    async def _answer_events() -> AsyncIterator[str]:
        state = ChatState(chat_id=str(chat.id), messages=context_to_langchain(context))
        config: RunnableConfig = {
            "configurable": {
                # One thread per *request*, not per conversation — the position
                # in the transcript makes it unique.
                #
                # Threading by chat id looks natural and is wrong here, in a way
                # that costs money rather than erroring. The database is the
                # transcript's source of truth, so this handler seeds the graph
                # with the full history every time; if the thread already held
                # the previous turns, `add_messages` would append the fresh
                # copies rather than recognise them (it matches on message id,
                # and these are rebuilt from rows each request). The context
                # would double every turn, silently.
                #
                # Per-request threads also match the Phase 2 criterion more
                # closely: each chat request becomes its own inspectable
                # execution rather than one ever-growing thread.
                "thread_id": f"{chat.id}:{next_position}",
                PERSIST_KEY: persist_answer,
                RECORD_SAFETY_KEY: record_safety,
            }
        }

        try:
            # `stream_mode=["custom"]` is what carries tokens: node-level updates
            # only arrive *after* a node returns, so without the custom channel a
            # streamed answer would land as one lump when `generate_answer`
            # finished. The nodes emit on it via `get_stream_writer()`.
            async for mode, payload in graph.astream(state, config=config, stream_mode=["custom"]):
                if mode != "custom":
                    continue
                if "token" in payload:
                    yield sse.event("token", {"text": payload["token"]})
                elif "safety" in payload:
                    # Forwarded as it happens rather than summarised at the end,
                    # because an output-stage refusal arrives *after* the client
                    # has already rendered tokens: the sooner it is told to drop
                    # them, the shorter the window in which they are on screen.
                    yield sse.event("safety", payload["safety"])

            # Read the outcome from the graph rather than from a variable the
            # loop happened to set: the checkpointed state is the record of what
            # ran, and reading it here is the same thing the exit-criterion test
            # inspects.
            final = (await graph.aget_state(config)).values

            # A refusal is an outcome, not an error: the system worked. It gets
            # its own terminal event so the client can distinguish "we declined"
            # from "something broke", and never reports it as a failure.
            blocked_at = final.get("blocked_at")
            if blocked_at is not None:
                outcome = final.get(
                    "output_safety" if blocked_at == SafetyStage.OUTPUT else "input_safety"
                )
                yield sse.event(
                    "blocked",
                    {
                        "stage": SafetyStage(blocked_at).value,
                        "categories": outcome.categories if outcome else [],
                        "explanation": outcome.explanation if outcome else "",
                        # Nothing was written. The client must discard whatever it
                        # streamed, and reloading the chat is what confirms it.
                        "persisted": False,
                    },
                )
                return

            answer: CompletionResponse | None = final.get("answer")
            message_id: str | None = final.get("persisted_message_id")
            if answer is None or message_id is None:
                yield sse.event("error", {"detail": "the graph did not produce a stored answer"})
                return

            yield sse.event(
                "done",
                {
                    "message_id": message_id,
                    "sequence_number": next_position,
                    # Surfaced rather than hidden: a truncated answer is not a
                    # complete one, and the client should be able to say so.
                    "truncated": answer.was_truncated,
                    # The handle that turns "this answer was poor" into a trace
                    # to read (docs/SPEC.md §11). Sent on the wire rather than
                    # only stored so the UI can offer the link without a second
                    # round trip.
                    "trace_id": current_trace_id(),
                    # The alias is the app's vocabulary; provider_model is what
                    # actually served it. Phase 5 persists both in `model_run`.
                    #
                    # `ModelAlias(...)` because a value read back out of a
                    # checkpoint is a plain string: msgpack restores the value,
                    # not the enum class. Coercing here keeps the wire payload
                    # identical to Phase 1's.
                    "alias": ModelAlias(answer.alias).value,
                    "provider_model": answer.provider_model,
                    "input_tokens": answer.input_tokens,
                    "output_tokens": answer.output_tokens,
                },
            )
        except (GatewayError, GraphError) as exc:
            # The stream is already open, so this cannot be a 502. An `error`
            # event is the only way left to tell the client, and it is why the
            # client must treat "stream ended without `done`" as a failure.
            yield sse.event("error", {"detail": str(exc)})

    return StreamingResponse(events(), media_type=sse.SSE_MEDIA_TYPE, headers=sse.SSE_HEADERS)
