"""Contract for `LearningSummary` — the Phase 3 exit criterion, at schema level.

"Malformed or incomplete summaries are rejected before persistence." Every test
here is one way a model output can be malformed or incomplete, and the assertion
is that it does not validate. No model and no database: this is the layer that
must reject bad shapes without either.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ai_core.schemas.summary import MAX_ITEMS, LearningSummary


def _valid(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Indexes and primary keys",
        "overview": (
            "A primary key uniquely identifies a row and implies a unique index, "
            "while an index is a separate structure that speeds lookups."
        ),
        "key_concepts": ["A primary key implies a unique index"],
        "distinctions": ["Primary key versus unique index"],
        "examples": [],
        "open_questions": [],
        "suggested_tags": ["databases"],
        "uncertainty_notes": [],
    }
    body.update(overrides)
    return body


def test_a_well_formed_summary_validates() -> None:
    summary = LearningSummary.model_validate(_valid())
    assert summary.title == "Indexes and primary keys"


# --- incomplete ----------------------------------------------------------------


@pytest.mark.parametrize("field", ["title", "overview", "key_concepts"])
def test_a_missing_required_field_is_rejected(field: str) -> None:
    """ "Incomplete" in the exit criterion, literally.

    These three are required because a summary without them is not a summary:
    nothing to list it by, nothing to read, and nothing learned.
    """
    body = _valid()
    del body[field]
    with pytest.raises(ValidationError):
        LearningSummary.model_validate(body)


def test_a_summary_that_learned_nothing_is_rejected() -> None:
    # An empty `key_concepts` is the model failing, not the conversation being
    # empty — a conversation worth summarising taught at least one thing.
    with pytest.raises(ValidationError):
        LearningSummary.model_validate(_valid(key_concepts=[]))


def test_optional_lists_may_be_absent_entirely() -> None:
    """Empty is legal where it is meaningful, which is why they have defaults.

    Plenty of conversations contrast nothing and leave nothing open. Requiring a
    distinction would make the model invent one, which is worse than an empty
    list.
    """
    body = _valid()
    for optional in ("distinctions", "examples", "open_questions", "suggested_tags"):
        del body[optional]
    summary = LearningSummary.model_validate(body)
    assert summary.distinctions == []
    assert summary.is_hedged is False


# --- malformed -----------------------------------------------------------------


def test_an_unknown_field_is_rejected() -> None:
    """`extra="forbid"`, and it matters more than it looks.

    Without it a model returning `{"titel": ..., "title": ...}` would validate
    and the typo'd content would be dropped in silence. docs/SPEC.md §8 layer 5
    lists unknown fields as a reject condition for exactly this reason.
    """
    with pytest.raises(ValidationError, match="Extra inputs"):
        LearningSummary.model_validate(_valid(hallucinated_field="anything"))


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_a_blank_list_entry_is_rejected(blank: str) -> None:
    # Padding to length. It renders as an empty bullet and means nothing.
    with pytest.raises(ValidationError):
        LearningSummary.model_validate(_valid(key_concepts=[blank]))


def test_a_blank_title_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LearningSummary.model_validate(_valid(title="   "))


def test_a_one_word_overview_is_rejected() -> None:
    # Bounded below because "Databases." is not a summary of anything.
    with pytest.raises(ValidationError):
        LearningSummary.model_validate(_valid(overview="Databases."))


def test_a_runaway_list_is_rejected() -> None:
    """A model that will not stop is a failure mode, not thoroughness.

    Unbounded, this arrives as a wall of text in the review UI — and the user is
    the one who has to read it before approving.
    """
    with pytest.raises(ValidationError):
        LearningSummary.model_validate(_valid(key_concepts=["item"] * (MAX_ITEMS + 1)))


def test_a_title_that_is_really_a_paragraph_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LearningSummary.model_validate(_valid(title="word " * 60))


def test_wrong_types_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LearningSummary.model_validate(_valid(key_concepts="not a list"))


# --- properties ----------------------------------------------------------------


def test_is_hedged_reports_whether_uncertainty_survived() -> None:
    """docs/SPEC.md §8 layer 4 requires a summary to preserve uncertainty.

    This property is what the Guardrails validator reads; the schema itself
    cannot require hedging, because a conversation that genuinely settled
    everything should not be forced to invent doubt.
    """
    assert LearningSummary.model_validate(_valid()).is_hedged is False
    assert LearningSummary.model_validate(_valid(open_questions=["Does X hold?"])).is_hedged
    assert LearningSummary.model_validate(_valid(uncertainty_notes=["Unsure"])).is_hedged


def test_a_summary_is_immutable() -> None:
    """A draft the user edits is a *new* value, not a mutated one — which is what
    keeps "what the model produced" and "what the user approved" distinguishable
    (CLAUDE.md invariant #5)."""
    summary = LearningSummary.model_validate(_valid())
    with pytest.raises(ValidationError):
        summary.title = "rewritten"  # type: ignore[misc]


def test_no_field_lets_a_model_mark_its_own_output_approved() -> None:
    """Invariant #5 as a shape assertion.

    Approval is an event recorded elsewhere, never a flag on model output — so
    there is nothing here a model could set to promote itself.
    """
    forbidden = {"approved", "approved_at", "is_approved", "status"}
    assert not (forbidden & set(LearningSummary.model_fields))
