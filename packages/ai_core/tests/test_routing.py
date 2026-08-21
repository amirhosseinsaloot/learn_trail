"""Contract for model routing (docs/SPEC.md §15, Phase 10).

No model, no network. Routing is a rule precisely so the routing *decision* is a
pure function that can be pinned exhaustively here, without spending anything.
"""

from __future__ import annotations

import pytest

from ai_core.models.aliases import ModelAlias
from ai_core.models.routing import (
    Difficulty,
    classify_difficulty,
    fallback_for,
    route,
)


@pytest.mark.parametrize(
    "question",
    [
        "What is a primary key?",
        "Define an index.",
        "Is Postgres relational?",
        "list the ACID properties",
    ],
)
def test_simple_lookup_questions_route_cheap(question: str) -> None:
    """A definition or a yes/no is what the fast model is for."""
    difficulty, alias = route(question)
    assert difficulty is Difficulty.SIMPLE
    assert alias is ModelAlias.LEARNING_FAST


@pytest.mark.parametrize(
    "question",
    [
        "Why does a B-tree stay balanced?",
        "Compare UUIDs and bigints as primary keys.",
        "How would you design a connection pool?",
        "Explain the trade-offs between READ COMMITTED and SERIALIZABLE.",
        "What is the difference between an index and a primary key?",
    ],
)
def test_analytical_questions_route_strong(question: str) -> None:
    """Reasoning across several things at once is the strong model's job.

    Each of these carries a marker word — why, compare, design, trade-off,
    difference — that distinguishes 'work it out' from 'look it up'.
    """
    difficulty, alias = route(question)
    assert difficulty is Difficulty.DIFFICULT
    assert alias is ModelAlias.LEARNING_DEEP


def test_a_long_question_is_difficult_on_length_alone() -> None:
    """More constraints to satisfy at once, even with no marker word."""
    long_question = "Given " + "a table with many columns and several indexes, " * 8 + "what next"
    assert classify_difficulty(long_question) is Difficulty.DIFFICULT


def test_two_questions_in_one_turn_are_difficult() -> None:
    assert classify_difficulty("What is an index? And when is it not worth it?") is (
        Difficulty.DIFFICULT
    )


def test_a_marker_word_must_be_whole() -> None:
    """`whyever` is not `why`; a substring must not trip the router."""
    # No marker word, short, single question -> simple.
    assert classify_difficulty("Name a whyever-style token") is Difficulty.SIMPLE


def test_budget_exhaustion_forces_the_cheap_path() -> None:
    """Cost-aware routing: a hard question is answered cheaply, not refused.

    The difficulty is still reported as assessed, so a trace shows the question
    was hard and was answered on the fast model anyway — the graceful degradation,
    made visible rather than hidden.
    """
    difficulty, alias = route("Why is this hard?", budget_exhausted=True)
    assert difficulty is Difficulty.DIFFICULT
    assert alias is ModelAlias.LEARNING_FAST


def test_the_strong_model_falls_back_to_the_fast_one() -> None:
    assert fallback_for(ModelAlias.LEARNING_DEEP) is ModelAlias.LEARNING_FAST


def test_the_fast_model_has_no_fallback() -> None:
    """It is the floor. Its failure is an error, not a silent downgrade to nothing."""
    assert fallback_for(ModelAlias.LEARNING_FAST) is None


def test_the_judge_alias_has_no_fallback() -> None:
    """`safety-judge` is not an answer model; falling it back would be meaningless."""
    assert fallback_for(ModelAlias.SAFETY_JUDGE) is None
