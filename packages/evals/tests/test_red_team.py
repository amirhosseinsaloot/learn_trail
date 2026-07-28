"""Contract for the red-team measurement (docs/SPEC.md §9, Phase 7).

No model, no network. The comparison logic is pure arithmetic over recorded
outcomes, which is deliberate: Phase 7's criterion is that a safety change can be
*measured*, and a measurement you can only obtain by spending money is one nobody
takes before and after a change.

The dataset assertions here are the other half — a comparison over a dataset with
no controls would compute a confident number that means nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from evals.red_team import (
    NOISE_TOLERANCE,
    AttackCase,
    AttackCategory,
    CaseOutcome,
    Posture,
    Verdict,
    compare,
    load_baseline,
    load_cases,
    save_baseline,
    summarise,
)


def _outcomes(
    *, attacks_through: int, attacks_total: int, controls_refused: int, controls_total: int
) -> list[CaseOutcome]:
    """Synthetic outcomes with the rates a test needs. No pipeline involved."""
    outcomes: list[CaseOutcome] = []
    for index in range(attacks_total):
        outcomes.append(
            CaseOutcome(
                case_id=f"attack-{index}",
                category=AttackCategory.INJECTION,
                kind="attack",
                action="allow" if index < attacks_through else "block",
            )
        )
    for index in range(controls_total):
        outcomes.append(
            CaseOutcome(
                case_id=f"control-{index}",
                category=AttackCategory.INJECTION,
                kind="control",
                action="block" if index < controls_refused else "allow",
            )
        )
    return outcomes


def _posture(
    *, attacks_through: int, attacks_total: int, controls_refused: int, controls_total: int
) -> Posture:
    return summarise(
        _outcomes(
            attacks_through=attacks_through,
            attacks_total=attacks_total,
            controls_refused=controls_refused,
            controls_total=controls_total,
        ),
        measured_at="2026-07-28T00:00:00+00:00",
    )


# --- what counts as refused -----------------------------------------------------


def test_a_warning_is_not_a_defence() -> None:
    """An attack that earned a warning still reached the model.

    Counting a warning as a block is the most flattering reading of these numbers
    and the one most likely to hide a regression: a change that downgraded every
    block to a warning would score as unchanged.
    """
    warned = CaseOutcome(
        case_id="a",
        category=AttackCategory.INJECTION,
        kind="attack",
        action="allow_with_warning",
    )
    assert warned.refused is False
    assert warned.is_failure is True


def test_require_review_counts_as_refused() -> None:
    """It stops the interaction pending a human, so the attack did not land."""
    outcome = CaseOutcome(
        case_id="a", category=AttackCategory.INJECTION, kind="attack", action="require_review"
    )
    assert outcome.refused is True
    assert outcome.is_failure is False


def test_a_refused_control_is_a_failure() -> None:
    """Both directions are failures, which is the whole point of two rates."""
    control = CaseOutcome(
        case_id="c", category=AttackCategory.INJECTION, kind="control", action="block"
    )
    assert control.is_failure is True


# --- the two rates --------------------------------------------------------------


def test_both_rates_are_computed() -> None:
    posture = _posture(attacks_through=3, attacks_total=10, controls_refused=1, controls_total=5)
    assert posture.attack_success_rate == pytest.approx(0.3)
    assert posture.false_refusal_rate == pytest.approx(0.2)


def test_failures_are_named() -> None:
    """A regression should say which case moved, not require a rerun to find out."""
    posture = _posture(attacks_through=2, attacks_total=4, controls_refused=1, controls_total=2)
    assert posture.failures == ["attack-0", "attack-1", "control-0"]


def test_an_empty_set_reports_zero_rather_than_dividing_by_zero() -> None:
    assert summarise([]).attack_success_rate == 0.0
    assert summarise([]).false_refusal_rate == 0.0


# --- the criterion: improved, harmed, or a trade ---------------------------------


def test_fewer_attacks_through_is_an_improvement() -> None:
    baseline = _posture(attacks_through=5, attacks_total=10, controls_refused=0, controls_total=10)
    candidate = _posture(attacks_through=1, attacks_total=10, controls_refused=0, controls_total=10)
    result = compare(baseline, candidate)
    assert result.verdict is Verdict.IMPROVED
    assert result.attack_success_delta == pytest.approx(-0.4)


def test_more_attacks_through_is_harm() -> None:
    baseline = _posture(attacks_through=1, attacks_total=10, controls_refused=0, controls_total=10)
    candidate = _posture(attacks_through=5, attacks_total=10, controls_refused=0, controls_total=10)
    assert compare(baseline, candidate).verdict is Verdict.HARMED


def test_more_false_refusals_is_harm_even_with_attacks_unchanged() -> None:
    """Blocking ordinary questions is a regression, not a side effect.

    Without this, "safety" could be improved indefinitely by making the product
    less useful, and the report would never say so.
    """
    baseline = _posture(attacks_through=2, attacks_total=10, controls_refused=0, controls_total=10)
    candidate = _posture(attacks_through=2, attacks_total=10, controls_refused=4, controls_total=10)
    result = compare(baseline, candidate)
    assert result.verdict is Verdict.HARMED
    assert "refused" in result.detail


def test_blocking_more_of_both_is_a_trade_not_an_improvement() -> None:
    """The single most important assertion in this phase.

    A change that stops more attacks *and* refuses more ordinary questions is
    exactly what a blunt tightening produces. Reporting it as `improved` — which
    an attack-success-rate-only metric would — is how a change that quietly broke
    the product gets merged with a green tick.
    """
    baseline = _posture(attacks_through=6, attacks_total=10, controls_refused=0, controls_total=10)
    candidate = _posture(attacks_through=1, attacks_total=10, controls_refused=5, controls_total=10)
    result = compare(baseline, candidate)

    assert result.verdict is Verdict.MIXED
    assert result.attack_success_delta < 0  # attacks did get better
    assert result.false_refusal_delta > 0  # and ordinary use got worse
    assert "trade" in result.detail


def test_a_change_within_noise_is_reported_as_unchanged() -> None:
    """The rails are a model, so two runs of one system do not match exactly.

    Without a tolerance every run would declare a verdict and none would mean
    anything — and the first spurious "harmed" would teach everyone to ignore it.
    """
    baseline = _posture(
        attacks_through=2, attacks_total=100, controls_refused=1, controls_total=100
    )
    candidate = _posture(
        attacks_through=4, attacks_total=100, controls_refused=2, controls_total=100
    )
    result = compare(baseline, candidate)
    assert result.verdict is Verdict.UNCHANGED
    assert abs(result.attack_success_delta) < NOISE_TOLERANCE


def test_a_per_category_regression_is_surfaced() -> None:
    """An overall rate can hide one category getting much worse.

    Injections improving while jailbreaks collapse nets out to "unchanged", and
    the person who made the change needs to see the second half.
    """
    baseline = Posture(
        measured_at="t0",
        attacks=20,
        attacks_succeeded=4,
        controls=10,
        controls_refused=0,
        by_category={
            "prompt_injection": {"attacks": 10, "succeeded": 4},
            "jailbreak": {"attacks": 10, "succeeded": 0},
        },
    )
    candidate = Posture(
        measured_at="t1",
        attacks=20,
        attacks_succeeded=4,
        controls=10,
        controls_refused=0,
        by_category={
            "prompt_injection": {"attacks": 10, "succeeded": 0},
            "jailbreak": {"attacks": 10, "succeeded": 4},
        },
    )
    result = compare(baseline, candidate)
    assert result.category_deltas["jailbreak"] == pytest.approx(0.4)
    assert result.category_deltas["prompt_injection"] == pytest.approx(-0.4)


# --- the baseline ---------------------------------------------------------------


def test_a_baseline_round_trips(tmp_path: Path) -> None:
    posture = _posture(attacks_through=1, attacks_total=10, controls_refused=0, controls_total=5)
    path = tmp_path / "baseline.json"
    save_baseline(posture, path)
    restored = load_baseline(path)
    assert restored is not None
    assert restored.attack_success_rate == posture.attack_success_rate
    assert restored.by_category == posture.by_category


def test_no_baseline_reads_as_none(tmp_path: Path) -> None:
    assert load_baseline(tmp_path / "absent.json") is None


# --- the dataset ----------------------------------------------------------------


def test_the_dataset_has_attacks_and_controls() -> None:
    """A red-team set of attacks alone is passed perfectly by a system that
    refuses everything, and the report would show a flawless attack success rate
    while the product was unusable."""
    cases = load_cases()
    assert sum(1 for case in cases if case.kind == "attack") >= 10
    assert sum(1 for case in cases if case.kind == "control") >= 5


def test_every_spec_category_is_covered() -> None:
    """docs/SPEC.md §9 lists the scenarios; an uncovered one measures nothing."""
    covered = {case.category for case in load_cases()}
    required = {
        AttackCategory.INJECTION,
        AttackCategory.JAILBREAK,
        AttackCategory.SYSTEM_PROMPT_EXTRACTION,
        AttackCategory.PII_LEAKAGE,
        AttackCategory.ENCODED,
        AttackCategory.MULTI_TURN,
    }
    assert required <= covered, f"uncovered: {sorted(c.value for c in required - covered)}"


def test_every_attack_category_has_a_control() -> None:
    """Otherwise a category's rate can only ever move one way.

    A category of pure attacks rewards any change that makes the pipeline more
    suspicious of it, with nothing to register the cost.
    """
    attacks = {case.category for case in load_cases() if case.kind == "attack"}
    controls = {case.category for case in load_cases() if case.kind == "control"}
    assert attacks - controls == set(), (
        "a category of pure attacks rewards any change that makes the pipeline "
        "more suspicious of it, with nothing to register the cost"
    )


def test_every_case_states_its_impact() -> None:
    """A regression is triaged by someone who needs to know what it costs.

    "The injection rail regressed" is a fact; "any pasted log becomes an
    instruction channel" is a priority.
    """
    thin = [case.id for case in load_cases() if len(case.impact) < 30]
    assert thin == []


def test_every_case_explains_why_it_exists() -> None:
    thin = [case.id for case in load_cases() if len(case.notes) < 40]
    assert thin == []


def test_unknown_fields_are_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AttackCase.model_validate(
            {
                "id": "x",
                "category": "prompt_injection",
                "kind": "attack",
                "messages": [{"role": "user", "content": "q"}],
                "notes": "x" * 40,
                "impact": "y" * 30,
                "typo_field": True,
            }
        )
