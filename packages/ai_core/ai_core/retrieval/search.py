"""Hybrid search over approved Learnings (docs/SPEC.md §8, Phase 8).

**What "hybrid" buys, concretely.** Semantic search finds a passage about
connection pooling when the question says "too many open database handles" — no
shared words at all. It also cheerfully returns the *nearest* thing when the
library contains nothing relevant, because a nearest neighbour always exists.
Lexical search does the opposite: it finds `pgvector` when you type `pgvector`,
and finds nothing when you paraphrase. Each one's failure is the other's strength,
which is the entire argument for running both.

**Combined by Reciprocal Rank Fusion, not by score.** The two halves produce
numbers that are not comparable — cosine distance is a distance in [0, 2],
`ts_rank` is an unbounded relevance score whose scale depends on document length
and term frequency. Normalising them onto a shared range means inventing a
mapping and then tuning a weight, and the weight would be fitted to whatever
handful of queries happened to get tried. RRF ignores the scores entirely and
uses only the *ranks*, which are directly comparable by construction.

This module builds queries and does not execute them: it takes a session from the
caller. `ai_core` importing `database` is permitted by docs/ARCHITECTURE.md §7,
and here it is unavoidable — the search *is* a query — but the session's lifetime
still belongs to the request that owns it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Float, Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Learning, LearningChunk

#: RRF's damping constant. 60 is the value from the original paper and the one
#: every implementation uses; it decides how sharply rank 1 outweighs rank 10.
#: Left at the published default deliberately — tuning it against this library's
#: dozen queries would be fitting noise.
RRF_K: Final = 60

#: How many candidates each half contributes before fusion. Wider than the final
#: result count on purpose: a chunk ranked 8th by one half and 40th by the other
#: is exactly the kind of result fusion exists to surface, and it can only do that
#: if both halves looked deep enough to see it.
CANDIDATE_DEPTH: Final = 20

#: Cosine distance beyond which a semantic hit is treated as no hit at all.
#:
#: **Why a floor is needed.** A nearest neighbour always exists. Without this,
#: "How do I make sourdough bread?" returns the five nearest chunks in a library
#: about databases, the endpoint reports `grounded: true`, and the user sees an
#: answer with five citations attached to a question nothing in their library
#: covers. The model does say the passages do not contain the answer — that part
#: works — but citations under a non-answer still read as sources.
#:
#: **Why 0.80.** Measured against a real three-Learning library rather than
#: guessed (`text-embedding-3-small`, cosine distance, nearest hit):
#:
#:     relevant question ..................... 0.215 - 0.338
#:     loosely related ("speed up a slow
#:       SQL query" against an index note) ... 0.744
#:     unrelated (bread, marathons, football)  0.887 - 0.974
#:
#: The gap between 0.751 and 0.887 is wide and clean; 0.80 sits in it. It keeps
#: the loosely-related question — which *should* find the index Learning — and
#: drops everything genuinely off-topic. Re-derive it after changing the
#: embedding model: these numbers are a property of that model's vector space and
#: not of this code.
#:
#: Applied to the semantic half only. The lexical half is self-limiting: a query
#: with no shared stems simply matches nothing.
MAX_SEMANTIC_DISTANCE: Final = 0.80


@dataclass(frozen=True)
class Retrieved:
    """One chunk, with everything needed to cite it.

    `learning_id` and `learning_title` are the criterion made concrete: the
    citation a caller emits is built from these, so it describes what was
    actually retrieved rather than what a model said about its own reasoning.
    """

    chunk_id: uuid.UUID
    learning_id: uuid.UUID
    learning_title: str
    chunk_index: int
    content: str
    #: Fused rank score. Comparable within one result set and meaningless across
    #: two — RRF produces an ordering, not a similarity.
    score: float
    #: Which half surfaced it: `semantic`, `lexical`, or `both`. Worth showing in
    #: a debug view, and the fastest way to notice that one half has silently
    #: stopped contributing (an unindexed column, a broken embedding).
    matched_by: str


def _live_learnings() -> Select[tuple[uuid.UUID, str, int, uuid.UUID, str]]:
    """Base select over chunks of Learnings that still exist.

    The `deleted_at IS NULL` filter is not a nicety. A soft-deleted Learning is
    one the user removed from their library, and answering out of it would be the
    product quoting something the user believed was gone.
    """
    return (
        select(
            LearningChunk.id,
            LearningChunk.content,
            LearningChunk.chunk_index,
            Learning.id.label("learning_id"),
            Learning.title.label("learning_title"),
        )
        .join(Learning, Learning.id == LearningChunk.learning_id)
        .where(Learning.deleted_at.is_(None))
    )


async def _semantic(
    db: AsyncSession, vector: list[float], depth: int
) -> list[tuple[uuid.UUID, int]]:
    """Chunk ids ranked by cosine distance, nearest first.

    `.cosine_distance()` emits pgvector's `<=>` operator, which is the one the
    HNSW index was built for. Any other distance function here would produce
    correct results by sequential scan and no error to say so.
    """
    distance = LearningChunk.embedding.cosine_distance(vector)
    statement = (
        _live_learnings()
        # The floor is a WHERE, not a post-filter, so the index does the work and
        # an off-topic query returns nothing rather than returning the least-bad
        # thing in the library. See MAX_SEMANTIC_DISTANCE for the measurements.
        .where(distance < MAX_SEMANTIC_DISTANCE)
        .order_by(distance)
        .limit(depth)
    )
    rows = (await db.execute(statement)).all()
    return [(row.id, rank) for rank, row in enumerate(rows, start=1)]


async def _lexical(db: AsyncSession, query: str, depth: int) -> list[tuple[uuid.UUID, int]]:
    """Chunk ids ranked by full-text relevance.

    `plainto_tsquery`, not `to_tsquery`: the input is a user's question, and
    `to_tsquery` demands operator syntax and raises on a bare sentence. A search
    box that 500s on a question mark is not a search box.
    """
    tsvector = func.to_tsvector(text("'english'"), LearningChunk.content)
    tsquery = func.plainto_tsquery(text("'english'"), query)
    statement = (
        _live_learnings()
        .where(tsvector.op("@@")(tsquery))
        .order_by(func.ts_rank(tsvector, tsquery).cast(Float).desc())
        .limit(depth)
    )
    rows = (await db.execute(statement)).all()
    return [(row.id, rank) for rank, row in enumerate(rows, start=1)]


def fuse(
    semantic: list[tuple[uuid.UUID, int]], lexical: list[tuple[uuid.UUID, int]]
) -> dict[uuid.UUID, tuple[float, str]]:
    """Reciprocal Rank Fusion: score by position, never by the halves' own numbers.

        score(d) = sum over halves of  1 / (RRF_K + rank(d))

    A chunk found by both halves scores higher than one found by either alone,
    without ever having to decide how many points a cosine distance is worth in
    `ts_rank` units. Pure and separately testable, which is why it is a function
    rather than a clause inside the query.
    """
    scores: dict[uuid.UUID, float] = {}
    sources: dict[uuid.UUID, set[str]] = {}
    for half, ranked in (("semantic", semantic), ("lexical", lexical)):
        for chunk_id, rank in ranked:
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
            sources.setdefault(chunk_id, set()).add(half)

    return {
        chunk_id: (score, "both" if len(sources[chunk_id]) == 2 else next(iter(sources[chunk_id])))
        for chunk_id, score in scores.items()
    }


async def search(
    db: AsyncSession, query: str, vector: list[float], *, limit: int = 5
) -> list[Retrieved]:
    """Hybrid search. Returns the top `limit` chunks, best first.

    Both halves run even when one returns nothing — an empty lexical result is a
    normal outcome for a paraphrased question, and short-circuiting on it would
    quietly turn hybrid search back into semantic search.
    """
    semantic = await _semantic(db, vector, CANDIDATE_DEPTH)
    lexical = await _lexical(db, query, CANDIDATE_DEPTH)
    fused = fuse(semantic, lexical)
    if not fused:
        return []

    best = sorted(fused.items(), key=lambda item: item[1][0], reverse=True)[:limit]
    wanted = [chunk_id for chunk_id, _ in best]

    rows = (await db.execute(_live_learnings().where(LearningChunk.id.in_(wanted)))).all()
    by_id = {row.id: row for row in rows}

    return [
        Retrieved(
            chunk_id=chunk_id,
            learning_id=by_id[chunk_id].learning_id,
            learning_title=by_id[chunk_id].learning_title,
            chunk_index=by_id[chunk_id].chunk_index,
            content=by_id[chunk_id].content,
            score=score,
            matched_by=matched_by,
        )
        for chunk_id, (score, matched_by) in best
        if chunk_id in by_id
    ]
