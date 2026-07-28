"""Contract for chunking and rank fusion.

No model, no database. These are the two pieces of retrieval that are pure
functions, and they are the two most worth pinning: chunking decides what a
citation will quote, and fusion decides what gets cited at all.

The query halves and the indexer need Postgres and the gateway; they are covered
by the endpoint tests and the phase test.
"""

from __future__ import annotations

import uuid

import pytest

from ai_core.retrieval import RRF_K, chunk_learning, fuse
from ai_core.retrieval.chunking import MAX_CHUNK_CHARS
from ai_core.schemas.summary import LearningSummary


def _summary(**overrides: object) -> LearningSummary:
    base: dict[str, object] = {
        "title": "Indexes and primary keys",
        "overview": (
            "A primary key uniquely identifies a row and implies a unique index, "
            "whereas an index is a separate structure that speeds up lookups."
        ),
        "key_concepts": ["A primary key implies a unique index"],
        "distinctions": ["A primary key is a constraint; an index is a structure"],
        "examples": [],
        "open_questions": [],
        "uncertainty_notes": [],
        "suggested_tags": [],
    }
    base.update(overrides)
    return LearningSummary.model_validate(base)


# --- chunking -------------------------------------------------------------------


def test_every_chunk_carries_the_learning_title() -> None:
    """A retrieved fragment is shown on its own and given to the model on its own.

    "an index is a separate structure" is unattributable without the title, and
    the model sees nothing else — so the heading is context, not decoration.
    """
    chunks = chunk_learning("Indexes and primary keys", _summary())
    assert chunks
    for chunk in chunks:
        assert chunk.content.startswith("Indexes and primary keys")


def test_sections_become_separate_chunks() -> None:
    """The whole argument for chunking something this short.

    Embedded as one vector, a question about a distinction competes with
    everything else the Learning happens to contain.
    """
    sections = {chunk.section for chunk in chunk_learning("t", _summary())}
    assert {"Overview", "Key concepts", "Distinctions"} <= sections


def test_empty_sections_are_skipped() -> None:
    """A chunk reading "Examples:" with nothing under it still embeds to
    something, and that something is occasionally a query's nearest neighbour."""
    sections = {chunk.section for chunk in chunk_learning("t", _summary())}
    assert "Examples" not in sections
    assert "Open questions" not in sections


def test_chunk_indexes_are_dense_and_ordered() -> None:
    """`chunk_index` is what a citation points at, so gaps would be a bug."""
    chunks = chunk_learning("t", _summary())
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunking_is_deterministic() -> None:
    """Re-indexing must be safe to run whenever there is doubt.

    If the same input produced different chunks, a re-index would quietly
    reshuffle what every stored citation refers to.
    """
    assert chunk_learning("t", _summary()) == chunk_learning("t", _summary())


def test_a_long_section_is_split_rather_than_truncated() -> None:
    """Losing the tail of a long overview would lose it from search silently."""
    # 40 sentences, ~1700 characters: comfortably over MAX_CHUNK_CHARS and still
    # inside `LearningSummary`'s own 2000-character ceiling on `overview`. The
    # first draft of this test used 200 sentences and the schema rejected it,
    # which is the schema doing its job — an overview that long is the model
    # reproducing the transcript rather than summarising it.
    long_overview = " ".join(f"Sentence number {n} about database indexing." for n in range(40))
    chunks = chunk_learning("t", _summary(overview=long_overview))
    overview_chunks = [c for c in chunks if c.section == "Overview"]
    assert len(overview_chunks) > 1
    # Nothing was dropped: the last sentence survives somewhere.
    assert any("Sentence number 39" in c.content for c in overview_chunks)


def test_chunks_stay_near_the_size_bound() -> None:
    long_overview = " ".join(f"Sentence number {n} about database indexing." for n in range(40))
    for chunk in chunk_learning("t", _summary(overview=long_overview)):
        # The heading is added after splitting, so allow for it.
        assert len(chunk.content) <= MAX_CHUNK_CHARS + 200


# --- rank fusion ----------------------------------------------------------------


def test_a_chunk_found_by_both_halves_outranks_one_found_by_either() -> None:
    """The whole point of running two searches.

    Agreement between two methods that fail in different ways is the strongest
    signal available, and RRF gets it without ever comparing a cosine distance to
    a ts_rank.
    """
    both, semantic_only, lexical_only = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fused = fuse(
        semantic=[(both, 2), (semantic_only, 1)],
        lexical=[(both, 2), (lexical_only, 1)],
    )
    assert fused[both][0] > fused[semantic_only][0]
    assert fused[both][0] > fused[lexical_only][0]
    assert fused[both][1] == "both"


def test_the_source_of_each_match_is_recorded() -> None:
    """The fastest way to notice a half has silently stopped contributing."""
    semantic, lexical = uuid.uuid4(), uuid.uuid4()
    fused = fuse(semantic=[(semantic, 1)], lexical=[(lexical, 1)])
    assert fused[semantic][1] == "semantic"
    assert fused[lexical][1] == "lexical"


def test_rank_order_is_preserved_within_a_half() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    fused = fuse(semantic=[(first, 1), (second, 2)], lexical=[])
    assert fused[first][0] > fused[second][0]


def test_the_score_uses_rank_not_position_in_the_list() -> None:
    """RRF's formula, pinned. A change here silently reorders every result."""
    chunk = uuid.uuid4()
    fused = fuse(semantic=[(chunk, 1)], lexical=[])
    assert fused[chunk][0] == pytest.approx(1.0 / (RRF_K + 1))


def test_fusing_nothing_returns_nothing() -> None:
    """An empty library is a normal state, not an error."""
    assert fuse(semantic=[], lexical=[]) == {}


def test_one_empty_half_still_produces_results() -> None:
    """A paraphrased question matches no keywords, and that must not zero the run.

    Short-circuiting on an empty lexical result would quietly turn hybrid search
    back into semantic search.
    """
    chunk = uuid.uuid4()
    assert fuse(semantic=[(chunk, 1)], lexical=[])[chunk][1] == "semantic"
