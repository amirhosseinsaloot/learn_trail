"""Contract for the flashcard schema (docs/SPEC.md §15, Phase 12).

No model. The schema is the line between "the model returned JSON" and "the model
returned usable flashcards", and every rejection below is a degenerate output that
is well-formed and worthless — the kind a `str` field would have let through.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_core.schemas.flashcards import MAX_CARDS, MIN_CARDS, Flashcard, FlashcardSet


def _cards(n: int) -> list[dict[str, str]]:
    return [{"front": f"Question {i}?", "back": f"Answer number {i}"} for i in range(n)]


def test_a_well_formed_set_validates() -> None:
    fs = FlashcardSet.model_validate({"cards": _cards(MIN_CARDS)})
    assert len(fs.cards) == MIN_CARDS


def test_a_card_whose_back_restates_its_front_is_rejected() -> None:
    """ "What is a B-tree?" / "What is a B-tree?" is the commonest useless output."""
    with pytest.raises(ValidationError, match="front and back must differ"):
        Flashcard.model_validate({"front": "A B-tree", "back": "a b-tree"})


def test_a_set_that_is_too_small_is_rejected() -> None:
    """One card is not a study session."""
    with pytest.raises(ValidationError):
        FlashcardSet.model_validate({"cards": _cards(MIN_CARDS - 1)})


def test_a_set_that_is_too_large_is_rejected() -> None:
    """Past the ceiling is the model padding, not being thorough."""
    with pytest.raises(ValidationError):
        FlashcardSet.model_validate({"cards": _cards(MAX_CARDS + 1)})


def test_duplicate_fronts_are_rejected() -> None:
    """Two cards asking the same thing is the model repeating itself."""
    dupes = [
        {"front": "What is an index?", "back": "a lookup structure"},
        {"front": "What is an index?", "back": "a structure that speeds lookups"},
        {"front": "What is a key?", "back": "a unique identifier"},
    ]
    with pytest.raises(ValidationError, match="ask something different"):
        FlashcardSet.model_validate({"cards": dupes})


def test_a_blank_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Flashcard.model_validate({"front": "   ", "back": "something"})


def test_unknown_fields_are_rejected() -> None:
    """A misspelled key would silently drop content, like every other schema here."""
    with pytest.raises(ValidationError):
        Flashcard.model_validate({"front": "q?", "back": "a", "hint": "leaked"})
