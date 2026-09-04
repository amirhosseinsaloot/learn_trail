"""The title a model may give a conversation (docs/SPEC.md §6, "Generating titles").

A title is a *label*, not knowledge: it names a chat in the sidebar and nothing
is derived from it. That is why this schema is small — but it is still a schema,
because model output reaches persistence here as everywhere else (CLAUDE.md
invariant #4), and the failure modes are real. An unbounded model writes a
sentence; a bounded one still likes to wrap its answer in quotes.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

#: Comfortably inside `chat.title`'s `String(200)` and the API's own bound. The
#: limit is not the column's, it is the sidebar's: a title that has to be
#: truncated to be displayed has already failed at being a memory cue.
MAX_TITLE_LENGTH = 80


#: Quote characters a model wraps a one-line answer in. Written as escapes rather
#: than literal glyphs so the curly pairs are unambiguous in source.
_QUOTE_PAIRS = (('"', '"'), ("'", "'"), ("\u201c", "\u201d"), ("\u2018", "\u2019"))


class ChatTitle(BaseModel):
    """One generated title for one conversation."""

    # `extra="forbid"` for the reason `LearningSummary` documents: a model
    # returning `{"titel": ...}` alongside the real field must be rejected, not
    # silently half-read.
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TITLE_LENGTH)
    ]

    @field_validator("title", mode="before")
    @classmethod
    def _unwrap(cls, value: object) -> object:
        """Strip the packaging a model puts around a short answer.

        Quoting the title and ending it with a full stop are presentation tics of
        asking for one line, not different content — `"Postgres index types."`
        and `Postgres index types` name the same conversation. Normalising them
        is not loosening validation: the length and non-blank rules below still
        apply, and a title that is genuinely too long or empty is still rejected.
        """
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        for opening, closing in _QUOTE_PAIRS:
            if len(stripped) >= 2 and stripped.startswith(opening) and stripped.endswith(closing):
                stripped = stripped[1:-1].strip()
        return stripped.rstrip(".").strip()
