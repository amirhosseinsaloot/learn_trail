"""Retrieval over approved Learnings (docs/SPEC.md §8, Phase 8).

Four pieces, deliberately separable:

- `chunking`  — a Learning becomes retrievable pieces. No model, no database.
- `embedding` — pieces become vectors, through the `learning-embedding` alias.
- `search`    — hybrid lexical + semantic query, fused by rank.
- `indexer`   — the write side: chunk, embed, replace.

Nothing here decides what an *answer* says. Retrieval returns passages and the id
of the Learning each came from; turning that into a cited answer is the graph's
job, and keeping the split means a citation is a fact about what was fetched
rather than a claim a model made about its own reasoning.
"""

from ai_core.retrieval.chunking import MAX_CHUNK_CHARS, Chunk, chunk_learning
from ai_core.retrieval.embedding import EMBEDDING_ALIAS, Embedded, embed, embed_query
from ai_core.retrieval.search import RRF_K, Retrieved, fuse, search

__all__ = [
    "EMBEDDING_ALIAS",
    "MAX_CHUNK_CHARS",
    "RRF_K",
    "Chunk",
    "Embedded",
    "Retrieved",
    "chunk_learning",
    "embed",
    "embed_query",
    "fuse",
    "search",
]
