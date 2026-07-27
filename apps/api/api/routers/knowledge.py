"""Summary draft and Learning endpoints (docs/SPEC.md §6, Phase 3).

The HTTP surface of the approval gate. A conversation becomes a draft; a draft
becomes a Learning only when this module receives an explicit approval request
(CLAUDE.md invariant #5).

**Approval resumes the graph rather than working around it.** The summary
workflow interrupts at `await_approval` and stays interrupted until a human
decides. It would have been simpler to have `POST /approve` write the `learning`
row directly and leave the graph's interrupt as decoration — and that is exactly
what would have made invariant #5 a comment instead of a mechanism. Instead the
draft id is generated *here*, before the run, so the interrupt's thread id is
knowable and the approval endpoint can resume that specific run.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from ai_core.agents.summariser import GeneratedSummary, SummaryGenerationError
from ai_core.graphs.summary import (
    APPLY_DECISION_KEY,
    LOAD_TRANSCRIPT_KEY,
    STORE_DRAFT_KEY,
    ReviewDecision,
    SummaryError,
    SummaryRejected,
)
from api.graph import summary_graph
from api.schemas import (
    LearningDetail,
    LearningEdit,
    LearningRead,
    SummaryContent,
    SummaryDraftRead,
)
from database.models import (
    ChangeSource,
    Chat,
    ChatStatus,
    DraftStatus,
    Learning,
    LearningRevision,
    SummaryDraft,
)
from database.session import session

router = APIRouter(tags=["knowledge"])

Session = Annotated[AsyncSession, Depends(session)]
SummaryGraph = Annotated[Any, Depends(summary_graph)]


def _thread_for(draft_id: uuid.UUID) -> str:
    """The checkpointer thread holding one draft's interrupted run.

    Keyed by draft rather than by chat: a chat can be summarised more than once
    (a rejected draft, then another attempt), and each attempt is its own
    suspended workflow waiting on its own decision.
    """
    return f"summary:{draft_id}"


# --- generating a draft --------------------------------------------------------


@router.post("/chats/{chat_id}/summary", status_code=status.HTTP_201_CREATED)
async def generate_summary(
    chat_id: uuid.UUID, db: Session, graph: SummaryGraph
) -> SummaryDraftRead:
    """Summarise a conversation into a draft awaiting review.

    Runs the summary graph until it interrupts for approval. What comes back is a
    *draft* — model output the user has not yet accepted.

    Calling this again replaces any pending draft for the chat, which is what
    "regenerate" means (docs/SPEC.md §15). A partial unique index enforces the
    one-pending-draft rule at the database level, so the replacement is not a
    convention this handler could forget.

    A summary that fails validation is a 422 and **nothing is written** — that is
    the Phase 3 exit criterion, and it holds because the graph raises before
    reaching its `store_draft` node.
    """
    chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no chat with id {chat_id}")
    if chat.status is ChatStatus.DELETED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"chat {chat_id} is deleted")
    if not chat.messages:
        raise HTTPException(status.HTTP_409_CONFLICT, f"chat {chat_id} has nothing to summarise")

    # Superseded rather than deleted: "the model proposed this and I asked for
    # another" is information Phase 6 evaluates on.
    await db.execute(
        update(SummaryDraft)
        .where(SummaryDraft.chat_id == chat_id, SummaryDraft.status == DraftStatus.PENDING)
        .values(status=DraftStatus.REJECTED)
    )
    await db.commit()

    # Generated here, before the run, so the interrupt's thread id is knowable and
    # `approve` can resume this exact workflow. See the module docstring.
    draft_id = uuid.uuid4()

    async def load_transcript(_: str) -> list[tuple[str, str]]:
        return [(message.role.value, message.content) for message in chat.messages]

    async def store_draft(generated: GeneratedSummary) -> str:
        db.add(
            SummaryDraft(
                id=draft_id,
                chat_id=chat_id,
                title=generated.summary.title,
                structured_content=generated.summary.model_dump(),
                prompt_version=generated.prompt_version,
            )
        )
        await db.commit()
        return str(draft_id)

    config: RunnableConfig = {
        "configurable": {
            "thread_id": _thread_for(draft_id),
            LOAD_TRANSCRIPT_KEY: load_transcript,
            STORE_DRAFT_KEY: store_draft,
        }
    }

    try:
        await graph.ainvoke({"chat_id": str(chat_id)}, config=config)
    except SummaryRejected as exc:
        # The exit criterion's failure path. 422 rather than 502: the model
        # answered, and what it produced was refused.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except (SummaryGenerationError, SummaryError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return SummaryDraftRead.model_validate(await _load_draft(db, draft_id))


@router.get("/chats/{chat_id}/summary")
async def get_pending_draft(chat_id: uuid.UUID, db: Session) -> SummaryDraftRead:
    """The draft currently awaiting review for a chat."""
    query = select(SummaryDraft).where(
        SummaryDraft.chat_id == chat_id, SummaryDraft.status == DraftStatus.PENDING
    )
    draft = (await db.execute(query)).scalar_one_or_none()
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no pending draft for chat {chat_id}")
    return SummaryDraftRead.model_validate(draft)


@router.patch("/summaries/{draft_id}")
async def edit_draft(draft_id: uuid.UUID, body: SummaryContent, db: Session) -> SummaryDraftRead:
    """Edit a draft before approving it.

    Edits land on the draft, not on a Learning: nothing here has been approved
    yet. The graph run stays interrupted throughout — editing is not a decision,
    and a user may edit repeatedly before making one.
    """
    draft = await _load_draft(db, draft_id)
    _require_pending(draft)

    draft.structured_content = body.model_dump()
    draft.title = body.title
    await db.commit()
    await db.refresh(draft, attribute_names=["updated_at"])
    return SummaryDraftRead.model_validate(draft)


# --- deciding ------------------------------------------------------------------


@router.post("/summaries/{draft_id}/approve", status_code=status.HTTP_201_CREATED)
async def approve_draft(draft_id: uuid.UUID, db: Session, graph: SummaryGraph) -> LearningDetail:
    """Promote a draft into a Learning. **The only path by which one is created.**

    Resumes the interrupted graph with the human's decision, so the promotion
    happens inside the workflow that produced the draft rather than beside it.

    The approved content is the draft's *current* content, edits included — the
    user approves what they are looking at, not what the model first produced.
    Revision 1 records `change_source=model` regardless, because the text
    originated as a generated draft; a later edit writes `human`.
    """
    draft = await _load_draft(db, draft_id)
    _require_pending(draft)

    learning_id = uuid.uuid4()

    async def apply_decision(_: str, decision: ReviewDecision) -> str:
        if decision is not ReviewDecision.APPROVE:  # pragma: no cover - guarded above
            raise SummaryError(f"unexpected decision {decision}")
        db.add(
            Learning(
                id=learning_id,
                source_chat_id=draft.chat_id,
                title=draft.title,
                structured_content=draft.structured_content,
            )
        )
        db.add(
            LearningRevision(
                learning_id=learning_id,
                revision_number=1,
                structured_content=draft.structured_content,
                change_source=ChangeSource.MODEL,
                note="approved from generated draft",
            )
        )
        draft.status = DraftStatus.APPROVED
        await db.commit()
        return str(learning_id)

    config: RunnableConfig = {
        "configurable": {
            "thread_id": _thread_for(draft_id),
            APPLY_DECISION_KEY: apply_decision,
        }
    }
    await graph.ainvoke(Command(resume=ReviewDecision.APPROVE.value), config=config)

    return LearningDetail.model_validate(await _load_learning(db, learning_id))


@router.post("/summaries/{draft_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_draft(draft_id: uuid.UUID, db: Session, graph: SummaryGraph) -> None:
    """Decline a draft. Nothing is promoted; the draft is kept as a record."""
    draft = await _load_draft(db, draft_id)
    _require_pending(draft)

    async def apply_decision(_: str, decision: ReviewDecision) -> str:
        draft.status = DraftStatus.REJECTED
        await db.commit()
        return str(decision)

    config: RunnableConfig = {
        "configurable": {
            "thread_id": _thread_for(draft_id),
            APPLY_DECISION_KEY: apply_decision,
        }
    }
    await graph.ainvoke(Command(resume=ReviewDecision.REJECT.value), config=config)


# --- the library ---------------------------------------------------------------


@router.get("/learnings")
async def list_learnings(
    db: Session,
    include_deleted: Annotated[bool, Query(description="Include soft-deleted.")] = False,
) -> list[LearningRead]:
    """My Learnings — everything the user has approved, most recent first."""
    query = (
        select(Learning).options(noload(Learning.revisions)).order_by(Learning.updated_at.desc())
    )
    if not include_deleted:
        query = query.where(Learning.deleted_at.is_(None))
    return [LearningRead.model_validate(row) for row in (await db.execute(query)).scalars().all()]


@router.get("/learnings/{learning_id}")
async def get_learning(learning_id: uuid.UUID, db: Session) -> LearningDetail:
    """One Learning with its full revision history."""
    return LearningDetail.model_validate(await _load_learning(db, learning_id))


@router.patch("/learnings/{learning_id}")
async def edit_learning(learning_id: uuid.UUID, body: LearningEdit, db: Session) -> LearningDetail:
    """Edit an approved Learning, writing a new revision.

    The previous content is not overwritten in place — it becomes history. That
    is what lets the library answer "what did this say when I approved it", which
    is the question that makes an edited Learning trustworthy rather than merely
    current.
    """
    learning = await _load_learning(db, learning_id)
    if learning.deleted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "restore this learning before editing it")

    highest = (
        await db.execute(
            select(func.max(LearningRevision.revision_number)).where(
                LearningRevision.learning_id == learning_id
            )
        )
    ).scalar_one()

    learning.title = body.content.title
    learning.structured_content = body.content.model_dump()
    db.add(
        LearningRevision(
            learning_id=learning_id,
            revision_number=(highest or 0) + 1,
            structured_content=body.content.model_dump(),
            # The user wrote this, so it is `human` — the column exists precisely
            # to keep authored text distinguishable from accepted text.
            change_source=ChangeSource.HUMAN,
            note=body.note,
        )
    )
    await db.commit()

    # Refresh `revisions` explicitly. Re-querying is not enough: the session's
    # identity map returns the *same* Learning instance, whose collection was
    # loaded before this insert, and `expire_on_commit=False` means the commit
    # did not invalidate it. Without this the write succeeds and the response
    # shows the history as it was a moment ago — so the user edits, and the page
    # tells them nothing happened.
    await db.refresh(learning, attribute_names=["revisions", "updated_at"])
    return LearningDetail.model_validate(learning)


@router.delete("/learnings/{learning_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_learning(learning_id: uuid.UUID, db: Session) -> None:
    """Soft-delete a Learning. Restorable, like a chat (docs/SPEC.md §6)."""
    learning = await _load_learning(db, learning_id)
    if learning.deleted_at is not None:
        return
    learning.deleted_at = func.clock_timestamp()
    await db.commit()


@router.post("/learnings/{learning_id}/restore")
async def restore_learning(learning_id: uuid.UUID, db: Session) -> LearningDetail:
    """Undo a soft delete."""
    learning = await _load_learning(db, learning_id)
    if learning.deleted_at is not None:
        learning.deleted_at = None
        await db.commit()
    return LearningDetail.model_validate(await _load_learning(db, learning_id))


# --- helpers -------------------------------------------------------------------


async def _load_draft(db: AsyncSession, draft_id: uuid.UUID) -> SummaryDraft:
    draft = (
        await db.execute(select(SummaryDraft).where(SummaryDraft.id == draft_id))
    ).scalar_one_or_none()
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no draft with id {draft_id}")
    return draft


async def _load_learning(db: AsyncSession, learning_id: uuid.UUID) -> Learning:
    learning = (
        await db.execute(select(Learning).where(Learning.id == learning_id))
    ).scalar_one_or_none()
    if learning is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no learning with id {learning_id}")
    return learning


def _require_pending(draft: SummaryDraft) -> None:
    """A decided draft cannot be decided again.

    409 rather than silently re-approving: approving twice would create a second
    Learning from the same draft, and the user would have no way to tell which
    one their library entry came from.
    """
    if draft.status is not DraftStatus.PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"draft {draft.id} was already {draft.status.value}",
        )
