"""Contract for the generated chat-title schema (docs/SPEC.md §6).

No model. What this pins down is the difference between "the model returned a
string" and "the model returned something that can go in a sidebar" — plus the
normalisation of the two tics a one-line prompt reliably produces.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_core.schemas.chat_title import MAX_TITLE_LENGTH, ChatTitle


def test_a_plain_title_validates() -> None:
    assert ChatTitle.model_validate({"title": "Postgres index types"}).title == (
        "Postgres index types"
    )


@pytest.mark.parametrize(
    "raw",
    ['"Postgres index types"', "'Postgres index types'", "“Postgres index types”"],
)
def test_a_quoted_title_is_unwrapped(raw: str) -> None:
    """Quoting the answer is presentation, not different content."""
    assert ChatTitle.model_validate({"title": raw}).title == "Postgres index types"


def test_a_trailing_full_stop_is_dropped() -> None:
    """A sidebar entry is a label, and labels do not end in a full stop."""
    assert ChatTitle.model_validate({"title": "Postgres index types."}).title == (
        "Postgres index types"
    )


def test_an_internal_full_stop_survives() -> None:
    """Only the *trailing* stop is packaging. `Node.js` is the subject itself."""
    assert ChatTitle.model_validate({"title": "Reading files in Node.js"}).title == (
        "Reading files in Node.js"
    )


def test_a_title_that_is_really_a_sentence_is_rejected() -> None:
    """Rejected, not truncated: a title cut mid-word is worse than no title, and
    the retry budget exists precisely so the model can be told to try again."""
    with pytest.raises(ValidationError):
        ChatTitle.model_validate({"title": "x" * (MAX_TITLE_LENGTH + 1)})


@pytest.mark.parametrize("raw", ["", "   ", '""'])
def test_a_blank_title_is_rejected(raw: str) -> None:
    """Blank would render as an invisible row in the chat list, which is the same
    failure the `ck_chat_title_not_blank` constraint exists to prevent."""
    with pytest.raises(ValidationError):
        ChatTitle.model_validate({"title": raw})


def test_an_unknown_field_is_rejected() -> None:
    """`{"titel": ..., "title": ...}` must fail rather than half-validate."""
    with pytest.raises(ValidationError):
        ChatTitle.model_validate({"title": "Indexes", "titel": "Indexes"})
