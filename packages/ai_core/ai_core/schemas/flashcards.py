"""Flashcards generated from an approved Learning (docs/SPEC.md §15, Phase 12).

A flashcard set is *study material derived from knowledge*, not knowledge itself.
It is generated on demand from an approved Learning and never stored: regenerating
is cheap, and persisting it would raise the question of whether an edited card is
"approved", which is a gate flashcards do not need (CLAUDE.md invariant #5 governs
what becomes durable knowledge, and a study aid is not that).

Every field is validated before it reaches a response (CLAUDE.md invariant #4).
The constraints below are the difference between "the model returned JSON" and "the
model returned usable flashcards" — a card whose front equals its back, or a set of
one, is well-formed and useless.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

#: A set has to be worth opening. One card is not a study session; forty is the
#: model padding. The range is what a person actually reviews in a sitting.
MIN_CARDS = 3
MAX_CARDS = 20

_Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Flashcard(BaseModel):
    """One card: a prompt and what it should recall."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The question or cue. Kept short — a flashcard front that is a paragraph is
    #: testing reading, not recall.
    front: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    #: The answer. Longer is allowed: a concise explanation is a fine back.
    back: _Text

    @model_validator(mode="after")
    def _front_and_back_differ(self) -> Flashcard:
        """A card whose answer restates its question teaches nothing.

        The commonest degenerate output — front "What is a B-tree?", back "A
        B-tree." — validates as JSON and fails as a flashcard, so it is rejected
        here rather than shown.
        """
        if self.front.strip().lower() == self.back.strip().lower():
            raise ValueError("a flashcard's front and back must differ")
        return self


class FlashcardSet(BaseModel):
    """A validated set of cards for one Learning."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cards: list[Flashcard] = Field(min_length=MIN_CARDS, max_length=MAX_CARDS)

    @model_validator(mode="after")
    def _fronts_are_distinct(self) -> FlashcardSet:
        """Two cards asking the same thing is the model repeating itself.

        Distinctness is checked on the front only: two cards may legitimately
        share phrasing on the back (several concepts that reduce to one idea), but
        two identical prompts are a padded set, not a thorough one.
        """
        fronts = [card.front.strip().lower() for card in self.cards]
        if len(set(fronts)) != len(fronts):
            raise ValueError("every flashcard must ask something different")
        return self
