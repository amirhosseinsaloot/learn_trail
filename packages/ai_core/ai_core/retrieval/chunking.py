"""Turning an approved Learning into retrievable pieces (docs/SPEC.md §8, Phase 8).

**Why a Learning is chunked at all, given it is already short.** A `LearningSummary`
has an overview, key concepts, distinctions, examples, open questions and
uncertainty notes. Embedded whole, all six become one vector, and a question about
a distinction competes with everything else the Learning happens to contain. The
retrieval that follows is then only as precise as the *smallest* thing indexed —
which is the argument for chunking, and it holds at a hundred words as well as at
a hundred pages.

**Chunked by section, not by character count.** LlamaIndex's `SentenceSplitter`
runs *within* a section rather than across the whole document. The structure is
already there and it is semantic: splitting a rendered blob every 512 characters
would cut the third key concept in half and glue it to the first example, which is
exactly the failure that makes a citation confusing to read.

Every chunk carries its Learning's title as a heading. That is not decoration: a
retrieved fragment reading "an index is a separate structure" is unattributable on
its own, and the model is given chunks with no other context.
"""

from __future__ import annotations

from typing import Final

from llama_index.core.node_parser import SentenceSplitter
from pydantic import BaseModel, ConfigDict, Field

from ai_core.schemas.summary import LearningSummary

#: Upper bound per chunk, in characters. Sections shorter than this — which is
#: most of them — are never split at all, so this is a ceiling rather than a
#: target. Large enough that a key concept and its explanation stay together;
#: small enough that a retrieved chunk is quotable in a citation.
MAX_CHUNK_CHARS: Final = 900

#: Carried between split chunks so a sentence cut at a boundary still has its
#: lead-in on both sides. Costs a little duplication in the index and buys
#: retrieval that does not depend on where the boundary happened to fall.
CHUNK_OVERLAP_CHARS: Final = 120

#: The order sections are rendered in, with the label each gets. Ordered so
#: `chunk_index` is stable across re-indexing: a Learning re-chunked after an
#: edit should produce recognisably the same sequence, or every citation's
#: position becomes meaningless.
SECTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("overview", "Overview"),
    ("key_concepts", "Key concepts"),
    ("distinctions", "Distinctions"),
    ("examples", "Examples"),
    ("open_questions", "Open questions"),
    ("uncertainty_notes", "Uncertainty"),
)


class Chunk(BaseModel):
    """One retrievable piece, before it has an embedding or a row."""

    model_config = ConfigDict(frozen=True)

    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1)
    #: Which part of the Learning this came from. Not persisted today — the
    #: column would be a fourth thing to keep in step with the schema — but
    #: carried here because the chunker knows it and a future filtered search
    #: ("only distinctions") is the obvious next use.
    section: str


def _sections(summary: LearningSummary) -> list[tuple[str, str]]:
    """Each non-empty section as `(label, text)`.

    Empty lists are skipped rather than rendered as an empty heading. A chunk
    reading "Examples:" with nothing under it would still embed to something, and
    that something would occasionally be the nearest neighbour of a real query.
    """
    rendered: list[tuple[str, str]] = []
    for field, label in SECTIONS:
        value = getattr(summary, field, None)
        if isinstance(value, str):
            if value.strip():
                rendered.append((label, value.strip()))
        elif isinstance(value, list) and value:
            body = "\n".join(f"- {item}" for item in value if str(item).strip())
            if body:
                rendered.append((label, body))
    return rendered


def chunk_learning(title: str, summary: LearningSummary) -> list[Chunk]:
    """Split one approved Learning into the pieces that will be indexed.

    Deterministic: the same input always produces the same chunks in the same
    order. Re-indexing is therefore a safe, repeatable operation rather than
    something that quietly reshuffles what every stored citation points at.
    """
    splitter = SentenceSplitter(
        chunk_size=MAX_CHUNK_CHARS,
        chunk_overlap=CHUNK_OVERLAP_CHARS,
        # Count characters, not tokens. The tokeniser LlamaIndex would otherwise
        # reach for is the *chat* model's, which is not the embedding model's, so
        # the count would be approximate anyway — and an approximate token budget
        # is worth less than an exact character one that is easy to reason about.
        tokenizer=lambda text: list(text),
    )

    chunks: list[Chunk] = []
    for label, body in _sections(summary):
        # The title is repeated on every chunk. A fragment retrieved on its own
        # is otherwise unattributable, and the model sees nothing but chunks.
        header = f"{title}\n{label}\n"
        for piece in splitter.split_text(body):
            text = f"{header}{piece.strip()}"
            chunks.append(Chunk(chunk_index=len(chunks), content=text, section=label))
    return chunks
