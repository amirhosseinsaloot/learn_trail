"""Keeping the index in step with the library (Phase 8).

**Replace, never patch.** Re-indexing a Learning deletes every chunk it has and
writes a fresh set. Diffing would be cheaper and is the wrong shape: an edited
Learning re-chunks differently, so "which old chunk does this new one correspond
to" has no answer, and a partial update leaves the index describing a document
that no longer exists. Deleting first makes the operation idempotent, which is
what allows a re-index to be run whenever there is any doubt.

**Nothing unapproved is ever indexed.** The function takes a `Learning` row, and
a `Learning` row exists only because a human approved it (CLAUDE.md invariant #5).
There is deliberately no path here that accepts a `SummaryDraft`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_core.retrieval.chunking import chunk_learning
from ai_core.retrieval.embedding import embed
from ai_core.schemas.summary import LearningSummary
from database.models import Learning, LearningChunk


async def index_learning(db: AsyncSession, learning: Learning) -> int:
    """(Re)index one approved Learning. Returns the number of chunks written.

    The embedding call happens *before* the delete so a gateway failure leaves the
    old index intact. Doing it the other way round would mean a transient provider
    error silently removed a Learning from search — the failure would look like
    "the library forgot something" rather than like an outage.
    """
    summary = LearningSummary.model_validate(learning.structured_content)
    chunks = chunk_learning(learning.title, summary)
    if not chunks:
        # A Learning with no renderable content. Clear any stale index for it and
        # say nothing was written, rather than leaving chunks of a previous version.
        await db.execute(delete(LearningChunk).where(LearningChunk.learning_id == learning.id))
        await db.commit()
        return 0

    embedded = await embed([chunk.content for chunk in chunks])

    await db.execute(delete(LearningChunk).where(LearningChunk.learning_id == learning.id))
    db.add_all(
        [
            LearningChunk(
                learning_id=learning.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                embedding=vector.vector,
                embedding_model=vector.model,
            )
            for chunk, vector in zip(chunks, embedded, strict=True)
        ]
    )
    await db.commit()
    return len(chunks)


async def index_all(db: AsyncSession) -> dict[str, int]:
    """Index every live approved Learning. Returns `{learning_id: chunk_count}`.

    For the initial build and for after an embedding-model change, which
    invalidates every stored vector at once — see the alias comment in
    infra/litellm/config.yaml on why that is a breaking change rather than a
    tuning knob.
    """
    learnings = (
        (await db.execute(select(Learning).where(Learning.deleted_at.is_(None)))).scalars().all()
    )
    return {str(learning.id): await index_learning(db, learning) for learning in learnings}


async def drop_index(db: AsyncSession, learning_id: uuid.UUID) -> None:
    """Remove one Learning's chunks.

    Rarely needed explicitly: the foreign key cascades on a hard delete. It exists
    for the *soft* delete path, where the row survives and search must stop
    returning it — the search query already filters on `deleted_at`, so this is
    belt and braces for a library that has grown large enough for the dead weight
    to matter.
    """
    await db.execute(delete(LearningChunk).where(LearningChunk.learning_id == learning_id))
    await db.commit()
