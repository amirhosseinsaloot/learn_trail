"""Contract for the safety decision model and the PII scan.

No model and no database. The rails themselves need a judge model and are
covered by the live checks in the phase test; everything here is the logic that
decides what a set of checks *means*, which must be testable without spending
anything.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_core.safety.decisions import SafetyAction, SafetyDecision, SafetyOutcome, SafetyStage
from ai_core.safety.pii import describe, find_pii

INPUT = SafetyStage.INPUT


def _decision(action: SafetyAction, *, categories: list[str] | None = None) -> SafetyDecision:
    return SafetyDecision.refuse(
        INPUT,
        "test_policy",
        "test@1",
        action=action,
        categories=categories or [],
        explanation=f"{action.value} for testing",
    )


# --- combining decisions --------------------------------------------------------


def test_an_outcome_with_no_checks_allows() -> None:
    # Vacuous, but worth pinning: it is the base case the combination rule builds
    # on, and an empty outcome that blocked would make every unchecked path fail.
    assert SafetyOutcome(stage=INPUT).action is SafetyAction.ALLOW


def test_the_strictest_decision_wins() -> None:
    """A check that says block has seen something the others did not.

    Combining by "most restrictive" rather than by majority or by last-wins is
    what stops a single permissive check from overriding a real finding.
    """
    outcome = SafetyOutcome(
        stage=INPUT,
        decisions=[
            SafetyDecision.allow(INPUT, "a", "v1"),
            _decision(SafetyAction.ALLOW_WITH_WARNING),
            _decision(SafetyAction.BLOCK),
        ],
    )
    assert outcome.action is SafetyAction.BLOCK
    assert outcome.blocks is True


def test_a_warning_does_not_block() -> None:
    outcome = SafetyOutcome(
        stage=INPUT,
        decisions=[
            SafetyDecision.allow(INPUT, "a", "v1"),
            _decision(SafetyAction.ALLOW_WITH_WARNING),
        ],
    )
    assert outcome.action is SafetyAction.ALLOW_WITH_WARNING
    assert outcome.blocks is False
    assert len(outcome.warnings) == 1


def test_require_review_blocks() -> None:
    """It means a human must look first, so continuing would defeat it."""
    assert _decision(SafetyAction.REQUIRE_REVIEW).blocks is True


def test_allowed_interactions_still_produce_a_decision() -> None:
    """The exit criterion is that every interaction has an *explicit* path.

    Recording nothing on the allow path would make "checked and fine"
    indistinguishable from "never checked", which is the thing the criterion is
    guarding against.
    """
    decision = SafetyDecision.allow(INPUT, "nemo_rails", "safety_rails@1")
    assert decision.action is SafetyAction.ALLOW
    assert decision.policy_version == "safety_rails@1"
    assert decision.severity == 0


def test_severity_is_derived_not_chosen() -> None:
    # Two call sites cannot disagree about how serious a block is.
    assert (
        _decision(SafetyAction.BLOCK).severity > _decision(SafetyAction.ALLOW_WITH_WARNING).severity
    )


def test_the_explanation_names_only_the_blocking_reasons() -> None:
    """A user told "blocked" needs to know which concern did it.

    Listing the checks that passed would bury the one that mattered.
    """
    outcome = SafetyOutcome(
        stage=INPUT,
        decisions=[
            SafetyDecision.refuse(
                INPUT,
                "pii",
                "v1",
                action=SafetyAction.ALLOW_WITH_WARNING,
                categories=["email"],
                explanation="found an email",
            ),
            SafetyDecision.refuse(
                INPUT,
                "rails",
                "v1",
                action=SafetyAction.BLOCK,
                categories=["jailbreak"],
                explanation="looks like an injection",
            ),
        ],
    )
    assert outcome.explanation == "looks like an injection"


def test_a_decision_is_immutable() -> None:
    """An audit record that can be edited after the fact is not an audit record."""
    decision = SafetyDecision.allow(INPUT, "a", "v1")
    with pytest.raises(ValidationError):
        decision.action = SafetyAction.BLOCK  # type: ignore[misc]


# --- PII ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("my email is someone@example.com", ["email"]),
        ("token sk-abcdefghijklmnop0123456789", ["api_key"]),
        ("-----BEGIN RSA PRIVATE KEY-----", ["private_key"]),
        ("card 4111 1111 1111 1111 please", ["credit_card"]),
    ],
)
def test_finds_structured_identifiers(text: str, expected: list[str]) -> None:
    assert find_pii(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "commit 8f2a4c1de9b7a3f5c6d8e0a2b4c6d8e0a2b4c6d8",  # a git sha
        "order number 1234567890123456789",  # long, but fails Luhn
        "version 1.2.3 released 2026-07-27",
        "the answer is 42",
    ],
)
def test_does_not_fire_on_ordinary_text(text: str) -> None:
    """False positives are the failure mode that matters here.

    A warning that appears on every commit hash is one the user learns to click
    past — at which point it no longer protects them from the real case.
    """
    assert find_pii(text) == []


def test_a_card_shaped_number_must_pass_luhn() -> None:
    # Same length and shape as the valid card above, one digit changed.
    assert find_pii("card 4111 1111 1111 1112 please") == []


def test_several_categories_are_all_reported() -> None:
    text = "email me@example.com and my key sk-abcdefghijklmnop0123456789"
    assert set(find_pii(text)) == {"email", "api_key"}


def test_findings_are_described_without_quoting_the_secret() -> None:
    """The audit record must not become a second copy of the credential."""
    described = describe(["api_key", "email"])
    assert "sk-" not in described
    assert "api key" in described.lower()
