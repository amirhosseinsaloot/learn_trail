"""Phase 7 — Red teaming

See docs/SPEC.md, "Phase 7 — Red teaming" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.phase


@pytest.mark.phase
def test_phase_7_exit_criterion() -> None:
    """Phase 7 — Red teaming.

    Exit criterion (verbatim, docs/SPEC.md):

        "You can measure whether a safety change improves or harms the system."

    The sentence asks for a *measurement*, and the obvious one is a trap. Attack
    success rate alone can be driven to zero by a system that refuses
    everything — so a change that halved it while doubling refusals of ordinary
    questions would report as a triumph while making the product useless. A
    measurement that cannot tell those two apart does not measure what the
    criterion is about.

    So five things are asserted.

    **Two rates, not one.** Attack success and false refusal, both computed, both
    free to move independently.

    **A trade is reported as a trade.** The `MIXED` verdict is the whole reason
    this phase is more than a test suite: a change that stops more attacks *and*
    refuses more ordinary questions is not an improvement, and calling it one is
    how a change that quietly broke the product merges on a green tick.

    **Harm is caught in both directions.** More attacks through is a regression;
    so is more ordinary questions refused with attacks unchanged.

    **Noise does not produce verdicts.** The rails are a model, so two runs of an
    unchanged system do not agree exactly. Without a tolerance every run would
    declare something, and the first spurious "harmed" would teach everyone to
    ignore all of them.

    **A "before" exists.** A comparison needs a recorded baseline, and that
    baseline must know which safety configuration it describes — otherwise a
    stale measurement is indistinguishable from a fresh one, which is exactly
    what the CI gate has to tell apart.

    **No model, no network.** The comparison is arithmetic over recorded
    outcomes. A measurement obtainable only by spending money is one nobody takes
    both before and after a change, which would leave the criterion technically
    satisfied and practically false.
    """
    import yaml
    from evals.red_team import (
        NOISE_TOLERANCE,
        AttackCategory,
        CaseOutcome,
        Posture,
        Verdict,
        compare,
        load_baseline,
        load_cases,
        requires_measurement,
        safety_fingerprint,
        summarise,
    )

    def posture(*, attacks_through: int, controls_refused: int, total: int = 10) -> Posture:
        outcomes = [
            CaseOutcome(
                case_id=f"a{index}",
                category=AttackCategory.INJECTION,
                kind="attack",
                action="allow" if index < attacks_through else "block",
            )
            for index in range(total)
        ] + [
            CaseOutcome(
                case_id=f"c{index}",
                category=AttackCategory.INJECTION,
                kind="control",
                action="block" if index < controls_refused else "allow",
            )
            for index in range(total)
        ]
        return summarise(outcomes, measured_at="t")

    # --- two rates, not one ----------------------------------------------------
    measured = posture(attacks_through=3, controls_refused=2)
    assert measured.attack_success_rate == pytest.approx(0.3)
    assert measured.false_refusal_rate == pytest.approx(0.2)

    # A warning is not a defence: the message still reached the model. Counting
    # one as a block is the most flattering reading available, and would let a
    # change that downgraded every block to a warning score as unchanged.
    warned = CaseOutcome(
        case_id="w", category=AttackCategory.INJECTION, kind="attack", action="allow_with_warning"
    )
    assert warned.refused is False

    # --- an improvement is recognised ------------------------------------------
    improved = compare(
        posture(attacks_through=6, controls_refused=0),
        posture(attacks_through=1, controls_refused=0),
    )
    assert improved.verdict is Verdict.IMPROVED

    # --- harm is caught in both directions -------------------------------------
    more_attacks = compare(
        posture(attacks_through=1, controls_refused=0),
        posture(attacks_through=6, controls_refused=0),
    )
    assert more_attacks.verdict is Verdict.HARMED, (
        "more attacks getting through must be a regression"
    )

    more_refusals = compare(
        posture(attacks_through=2, controls_refused=0),
        posture(attacks_through=2, controls_refused=5),
    )
    assert more_refusals.verdict is Verdict.HARMED, (
        "refusing more ordinary questions must be a regression; without this, safety "
        "could be improved indefinitely by making the product useless"
    )

    # --- a trade is reported as a trade ----------------------------------------
    trade = compare(
        posture(attacks_through=6, controls_refused=0),
        posture(attacks_through=1, controls_refused=5),
    )
    assert trade.verdict is Verdict.MIXED, (
        "a change that stopped more attacks by refusing more ordinary questions was "
        "reported as an improvement; that is the failure this phase exists to prevent"
    )
    assert trade.attack_success_delta < 0
    assert trade.false_refusal_delta > 0

    # --- noise does not produce verdicts ---------------------------------------
    within_noise = compare(
        posture(attacks_through=2, controls_refused=1, total=100),
        posture(attacks_through=4, controls_refused=2, total=100),
    )
    assert within_noise.verdict is Verdict.UNCHANGED
    assert abs(within_noise.attack_success_delta) < NOISE_TOLERANCE

    # --- the dataset can support the measurement -------------------------------
    cases = load_cases()
    attacks = {case.category for case in cases if case.kind == "attack"}
    controls = {case.category for case in cases if case.kind == "control"}
    assert attacks, "the dataset contains no attacks"
    uncounterweighted = sorted(category.value for category in attacks - controls)
    assert uncounterweighted == [], (
        "an attack category has no control. A category of pure attacks rewards any "
        f"change that makes the pipeline more suspicious of it: {uncounterweighted}"
    )

    required = {
        AttackCategory.INJECTION,
        AttackCategory.JAILBREAK,
        AttackCategory.SYSTEM_PROMPT_EXTRACTION,
        AttackCategory.PII_LEAKAGE,
        AttackCategory.ENCODED,
        AttackCategory.MULTI_TURN,
    }
    uncovered = sorted(category.value for category in required - attacks)
    assert uncovered == [], f"docs/SPEC.md §9 scenarios not covered: {uncovered}"

    # --- a "before" exists, and knows what it describes ------------------------
    # A *fresh* measurement must carry the fingerprint too, not just the one
    # already on disk. Asserting only the recorded baseline let a mutation that
    # stopped recording it pass — the committed file still had the field, so the
    # gate would keep passing until the next measurement silently dropped it.
    assert posture(attacks_through=0, controls_refused=0).safety_fingerprint, (
        "a newly measured posture does not record the safety configuration it "
        "describes, so the next baseline would be uncomparable"
    )

    baseline = load_baseline()
    assert baseline is not None, (
        "no baseline has been recorded, so there is nothing to measure a change against"
    )
    assert baseline.safety_fingerprint, (
        "the baseline does not record which safety configuration it describes, so a "
        "stale measurement is indistinguishable from a fresh one"
    )
    assert baseline.safety_fingerprint == safety_fingerprint(), (
        "the safety configuration has changed since the baseline was measured; run "
        "`make redteam` to find out whether that change improved or harmed the system"
    )

    # --- the gate recognises safety changes, and only those --------------------
    for path in [
        "packages/ai_core/ai_core/safety/rails/v2.yml",
        "packages/ai_core/ai_core/safety/pipeline.py",
        "infra/litellm/config.yaml",
    ]:
        assert requires_measurement([path]) == [path], f"{path} must require a measurement"

    for path in ["README.md", "apps/web/src/app/page.tsx", "prompts/learning_summary/v1.toml"]:
        # The summary prompt is deliberately absent: it does not change what gets
        # blocked, and demanding a paid red-team run for it is the over-triggering
        # that gets a gate switched off.
        assert requires_measurement([path]) == [], f"{path} must not require a measurement"

    # --- and it is wired to a merge --------------------------------------------
    workflow_path = Path(__file__).resolve().parents[2] / ".github/workflows/evaluation-gate.yml"
    workflow: dict[Any, Any] = yaml.safe_load(workflow_path.read_text())
    jobs = workflow["jobs"]
    assert "red-team" in jobs, "no CI job checks the safety baseline"

    invocations = [str(step.get("run", "")) for step in jobs["red-team"]["steps"]]
    assert any("redteam-gate" in run for run in invocations), (
        "the red-team job exists but never checks the baseline"
    )
    # It must not *measure* in CI: that needs a provider credential there and
    # would spend money on every push.
    assert not any("redteam run" in run or "redteam accept" in run for run in invocations), (
        "the CI job measures the posture; it should verify the recorded baseline instead"
    )
