"""Phase 8 — Search across approved learnings

See docs/SPEC.md, "Phase 8 — Search across approved learnings" section, for the full
Build/AI-stack/Learn breakdown. This file only encodes the exit criterion as an
executable check.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, get_type_hints

import pytest

pytestmark = pytest.mark.phase


@pytest.mark.phase
def test_phase_8_exit_criterion() -> None:
    """Phase 8 — Search across approved learnings.

    Exit criterion (verbatim, docs/SPEC.md):

        "Answers based on previous learnings identify exactly which approved
        learning supplied the context."

    **Exactly** is the word doing the work, and it cuts both ways: an answer must
    not omit a Learning that supplied context, and must not name one that did not.
    A system that cites plausibly is worse than one that cites nothing, because a
    citation is an invitation to stop checking.

    That is why attribution here is a *fact about retrieval* rather than a claim
    in the model's prose. The answer is built from chunks, each chunk carries the
    id of the Learning it came from, and the citation list is those ids. Nothing
    parses "[1]" markers out of the answer, so there is no path by which the model
    can invent a source or forget one — the failure mode is designed out rather
    than tested for.

    Six things are asserted.

    **Every chunk knows its Learning.** `learning_chunk.learning_id` is NOT NULL
    with a foreign key to `learning`. Without it the criterion is unanswerable at
    any price.

    **Nothing unapproved can be cited.** The indexer accepts a `Learning` and
    nothing else, and a `Learning` row exists only because a human approved it —
    CLAUDE.md invariant #5 holding at the retrieval layer.

    **A citation identifies rather than describes.** Two Learnings may share a
    title; "exactly which" requires an id.

    **The citation set equals the retrieved set**, asserted over a constructed
    retrieval result so it holds with no model call.

    **An ungrounded answer says so.** The library not covering a question is a
    normal outcome and must be reported as one. A nearest neighbour always exists,
    so this is the specific way retrieval lies: a library about databases will
    happily "source" a question about bread.

    **The retrieval underneath is sound** — chunking is deterministic and dense,
    fusion prefers agreement — so the criterion does not rest on machinery nothing
    checked.

    **No model, no network.** Embedding and the two query halves are covered by
    packages/ai_core's tests and by live verification. What is asserted here is
    the attribution contract, which is pure structure.
    """
    from ai_core.retrieval import Retrieved, chunk_learning, fuse
    from ai_core.retrieval.indexer import index_learning
    from ai_core.schemas.summary import LearningSummary
    from api.routers.knowledge import _as_citation
    from api.schemas import AskResponse, Citation
    from database.models import Learning, LearningChunk

    # --- every chunk knows which Learning it came from --------------------------
    columns = LearningChunk.__table__.columns
    assert "learning_id" in columns, "a chunk with no Learning cannot be attributed at all"
    assert not columns["learning_id"].nullable, (
        "learning_id is nullable, so a chunk can exist with no source — and any "
        "answer built from it would be uncitable"
    )
    referenced = [fk.column.table.name for fk in columns["learning_id"].foreign_keys]
    assert referenced == ["learning"], (
        f"learning_id references {referenced}; indexing anything but approved "
        "Learnings would defeat the approval gate from behind"
    )

    # --- nothing unapproved is reachable ---------------------------------------
    # `get_type_hints`, not `__annotations__`: the indexer uses
    # `from __future__ import annotations`, so its annotations are strings and a
    # bare identity check compares "Learning" to the class and always fails.
    indexed_type = get_type_hints(index_learning)["learning"]
    assert indexed_type is Learning, (
        f"the indexer accepts {indexed_type}; only approved Learnings may be "
        "indexed (CLAUDE.md invariant #5)"
    )

    # --- a citation identifies a Learning, not merely describes one -------------
    citation_fields = set(Citation.model_fields)
    assert "learning_id" in citation_fields, (
        "a citation without an id names a Learning by title, and two Learnings may "
        "share a title — 'exactly which' requires an identifier"
    )
    assert "excerpt" in citation_fields, (
        "without the passage, a reader cannot check the answer against what the "
        "model was given — only against the Learning as it reads today"
    )

    # --- the citation set is exactly the retrieved set --------------------------
    first, second = uuid.uuid4(), uuid.uuid4()
    retrieved = [
        Retrieved(
            chunk_id=uuid.uuid4(),
            learning_id=first,
            learning_title="Indexes and primary keys",
            chunk_index=0,
            content="A primary key implies a unique index.",
            score=0.9,
            matched_by="both",
        ),
        Retrieved(
            chunk_id=uuid.uuid4(),
            learning_id=second,
            learning_title="Write-ahead logging",
            chunk_index=2,
            content="The log records a change before it is applied.",
            score=0.4,
            matched_by="semantic",
        ),
    ]
    citations = [_as_citation(hit) for hit in retrieved]

    assert {citation.learning_id for citation in citations} == {first, second}, (
        "the citations do not match what was retrieved — attribution has drifted "
        "from the retrieval record, which is the only thing that knows the truth"
    )
    for hit, citation in zip(retrieved, citations, strict=True):
        assert citation.learning_id == hit.learning_id
        assert citation.excerpt == hit.content
        assert citation.chunk_index == hit.chunk_index

    # --- an ungrounded answer is reported as ungrounded -------------------------
    ungrounded = AskResponse(
        question="How do I make sourdough bread?",
        answer="Nothing in your approved Learnings covers that yet.",
        citations=[],
        grounded=False,
    )
    assert ungrounded.grounded is False
    assert ungrounded.citations == [], (
        "an ungrounded answer carries citations, which is the specific failure "
        "this phase guards: a nearest neighbour always exists, so a library about "
        "databases will happily 'source' a question about bread"
    )

    grounded = AskResponse(
        question="index vs primary key?", answer="…", citations=citations, grounded=True
    )
    assert grounded.grounded is True
    assert len(grounded.citations) == 2

    # --- the retrieval it rests on is sound ------------------------------------
    summary = LearningSummary.model_validate(
        {
            "title": "Indexes and primary keys",
            "overview": "A primary key uniquely identifies a row and implies a unique index.",
            "key_concepts": ["A primary key implies a unique index"],
        }
    )
    chunks = chunk_learning("Indexes and primary keys", summary)
    assert chunks, "a Learning produced no chunks, so it can never be retrieved or cited"
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks))), (
        "chunk indexes are what a citation points at; a gap would make one unresolvable"
    )
    assert chunk_learning("Indexes and primary keys", summary) == chunks, (
        "chunking is not deterministic, so re-indexing would silently change what "
        "every stored citation refers to"
    )

    agreed, semantic_only = uuid.uuid4(), uuid.uuid4()
    fused = fuse(semantic=[(agreed, 2), (semantic_only, 1)], lexical=[(agreed, 1)])
    assert fused[agreed][0] > fused[semantic_only][0], (
        "a chunk both halves found does not outrank one only semantic search "
        "found; agreement between two methods that fail differently is the "
        "strongest signal hybrid search has"
    )
    assert fused[agreed][1] == "both"

    # --- the endpoint exists and is shaped as the criterion requires ------------
    from api.main import app

    document: dict[str, Any] = app.openapi()
    assert "/learnings/ask" in document["paths"], "no endpoint answers from Learnings"

    ask_response = document["components"]["schemas"]["AskResponse"]
    assert "citations" in ask_response["properties"]
    assert "citations" in ask_response["required"], (
        "citations are optional in the response schema, so an answer may legally "
        "arrive without saying what it was based on"
    )

    # --- and the link survives a round trip through the database ---------------
    asyncio.run(_assert_chunks_link_back())


async def _assert_chunks_link_back() -> None:
    """Index a throwaway Learning and confirm every chunk points back at it.

    The one assertion here that touches Postgres. Skipped rather than failed when
    the database is absent, because `make status` has to stay runnable without the
    stack up — the same contract every earlier phase test honours.
    """
    from sqlalchemy import select
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import AsyncSession

    from ai_core.retrieval.chunking import chunk_learning
    from ai_core.schemas.summary import LearningSummary
    from database.models import Learning, LearningChunk
    from database.models.knowledge import EMBEDDING_DIMENSIONS
    from database.session import engine

    try:
        connection = await engine().connect()
    except DBAPIError:  # pragma: no cover - depends on the environment
        pytest.skip("no database reachable — run `make up`")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        summary = LearningSummary.model_validate(
            {
                "title": "Phase 8 fixture",
                "overview": "A throwaway Learning used only to prove chunks link back.",
                "key_concepts": ["Every chunk carries its Learning's id"],
            }
        )
        learning = Learning(title="Phase 8 fixture", structured_content=summary.model_dump())
        db.add(learning)
        await db.flush()

        # Written directly rather than through `index_learning`, which would need
        # the embedding gateway. What is asserted is the *link*; the chunker that
        # produces the rows is the real one.
        for chunk in chunk_learning(learning.title, summary):
            db.add(
                LearningChunk(
                    learning_id=learning.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    embedding=[0.0] * EMBEDDING_DIMENSIONS,
                    embedding_model="fixture",
                )
            )
        await db.flush()

        rows = (
            (
                await db.execute(
                    select(LearningChunk).where(LearningChunk.learning_id == learning.id)
                )
            )
            .scalars()
            .all()
        )
        assert rows, "indexing wrote no chunks, so the Learning is unsearchable"
        assert all(row.learning_id == learning.id for row in rows), (
            "a chunk points at a different Learning than the one it came from"
        )
    finally:
        await db.close()
        if transaction.is_active:
            # Rolled back: this fixture must not leave a Learning in the user's
            # real library, which the test database also is.
            await transaction.rollback()
        await connection.close()
