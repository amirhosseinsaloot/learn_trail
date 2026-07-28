"""Vectors, through the gateway (docs/SPEC.md §8, Phase 8).

Nothing here names an embedding model. `learning-embedding` is an alias like
every other (CLAUDE.md invariant #2), so swapping `text-embedding-3-small` for a
local model in Phase 11 is an edit to infra/litellm/config.yaml and nothing else.

**The model that produced a vector is returned alongside it, always.** Embeddings
from two models are not comparable — they occupy different spaces, and a library
indexed with one but queried with another returns confident nonsense rather than
an error. `learning_chunk.embedding_model` is what makes that detectable, and it
can only be recorded if the embedding call says what it used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import openai

from ai_core.models.gateway import GatewayError, client

#: The alias, not a model. See the module docstring.
EMBEDDING_ALIAS: Final = "learning-embedding"

#: How many texts to send per request. The provider accepts far more, but a batch
#: that fails takes everything in it with it, and re-embedding a whole library
#: because one chunk was malformed is a poor trade for a slightly lower request
#: count.
BATCH_SIZE: Final = 64


@dataclass(frozen=True)
class Embedded:
    """One text and the vector it produced."""

    text: str
    vector: list[float]
    #: The *provider* model the gateway actually used, not the alias. This is what
    #: goes on the row: an alias that gets repointed would otherwise make every
    #: historical vector claim to be something it is not.
    model: str


async def embed(texts: list[str]) -> list[Embedded]:
    """Embed a batch of texts, in order.

    Order is part of the contract: the caller pairs the results back up with the
    chunks by position, so a reordered response would attach every vector to the
    wrong text — a failure that produces no error and ruins every search result.
    The provider preserves order and returns an explicit `index` on each item;
    this sorts by it rather than trusting the sequence.
    """
    if not texts:
        return []

    embedded: list[Embedded] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        try:
            response = await client().embeddings.create(model=EMBEDDING_ALIAS, input=batch)
        except openai.APIError as exc:
            raise GatewayError(f"{EMBEDDING_ALIAS} call failed: {exc}") from exc

        for item in sorted(response.data, key=lambda datum: datum.index):
            embedded.append(
                Embedded(text=batch[item.index], vector=list(item.embedding), model=response.model)
            )
    return embedded


async def embed_query(text: str) -> Embedded:
    """Embed one search query.

    Separate from `embed` only for readability at the call site — the query and
    the documents *must* go through the same model, and giving them one code path
    is what guarantees it.
    """
    results = await embed([text])
    if not results:  # pragma: no cover - unreachable for a non-empty string
        raise GatewayError("the embedding call returned nothing for a non-empty query")
    return results[0]
