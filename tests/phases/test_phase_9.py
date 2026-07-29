"""Phase 9 — Prompt optimization

See docs/SPEC.md, "Phase 9 — Prompt optimization" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.phase


@pytest.mark.phase
def test_phase_9_exit_criterion() -> None:
    """Phase 9 — Prompt optimization.

    Exit criterion (verbatim, docs/SPEC.md):

        "The optimized program performs better on held-out examples, not only its
        optimization set."

    The sentence is about **overfitting**, and its second clause is the whole
    test. Any optimizer improves its training score — that is the number it
    climbs — so an improvement there is evidence of nothing. What has to be
    demonstrable is that the apparatus can tell a gain that generalised from one
    that did not.

    Five things are asserted, and one is deliberately *not*.

    **The split is disjoint and deterministic.** A case that drifted between
    train and held-out across runs would invalidate every comparison, silently.

    **The optimizer is given train only.** Asserted against the source: `held_out`
    must not appear before the optimizer's `compile` call. A comment promising
    this would be worth nothing.

    **Held-out is what decides.** `improved` reads the held-out delta, never the
    train delta.

    **Overfitting is named, not hidden.** A run that gains on train and not on
    held-out reports `overfitted` — the distinction the criterion is about.

    **Noise does not produce verdicts.** `MIN_IMPROVEMENT` exists because the
    metric is not bit-reproducible, and a phase about not fooling yourself must
    not declare victory on a difference it cannot distinguish from a rerun.

    **What is deliberately not asserted: that this repository's optimized prompt
    is better.** Four consecutive real runs alternated IMPROVED / OVERFITTED /
    IMPROVED / OVERFITTED, because COPRO is a stochastic search that lands on a
    different instruction each time — repeated runs are not repeated measurements
    of one thing. Nine cases cannot certify a particular prompt. Asserting that
    it can would make this test a fixed claim about a coin flip, and would be the
    exact failure docs/SPEC.md names: "optimization without a trustworthy
    evaluation set only produces confidently optimized noise."

    **No model, no network.** Every assertion is over the split, the comparison
    arithmetic and the source of the runner. The optimization itself costs money
    and is run by `make optimize`.
    """
    from evals.optimize import (
        MIN_IMPROVEMENT,
        TRAIN_FRACTION,
        Comparison,
        load_cases,
        split,
    )

    # --- the split is disjoint, deterministic, and non-trivial -----------------
    train, held_out = split()
    train_ids = {case.id for case in train}
    held_out_ids = {case.id for case in held_out}

    assert train_ids, "the optimizer would have nothing to learn from"
    assert held_out_ids, (
        "there is no held-out set, so the criterion's second clause cannot be evaluated at all"
    )
    assert train_ids & held_out_ids == set(), (
        f"a case appears in both splits: {sorted(train_ids & held_out_ids)}. Any "
        "comparison would then be partly a measurement of memorisation"
    )
    assert len(train) + len(held_out) == len(load_cases()), "the split drops cases"
    assert 0.0 < TRAIN_FRACTION < 1.0

    # Deterministic: the same call twice gives the same partition. A seeded
    # shuffle would satisfy this and still move when the seed or the RNG changed;
    # asserting it here is what makes the sorted-order choice load-bearing.
    again_train, again_held_out = split()
    assert [case.id for case in again_train] == [case.id for case in train]
    assert [case.id for case in again_held_out] == [case.id for case in held_out]

    # --- held-out is what decides ---------------------------------------------
    # Gained on train, lost on held-out: the textbook overfit. It must not read as
    # an improvement, whatever the training numbers say.
    overfit = Comparison(
        baseline_train=0.80,
        baseline_held_out=0.79,
        candidate_train=0.90,
        candidate_held_out=0.71,
        instruction="…",
    )
    assert overfit.improved is False, (
        "a candidate that gained on its own set and lost on unseen data was "
        "reported as an improvement — the exact failure the criterion names"
    )
    assert overfit.overfitted is True
    assert overfit.verdict() == "overfitted"

    # Gained on held-out: an improvement, even though train did not move at all.
    generalised = Comparison(
        baseline_train=1.00,
        baseline_held_out=0.71,
        candidate_train=1.00,
        candidate_held_out=0.88,
        instruction="…",
    )
    assert generalised.improved is True
    assert generalised.verdict() == "improved"

    # A large training gain cannot buy the verdict on its own.
    train_only = Comparison(
        baseline_train=0.10,
        baseline_held_out=0.80,
        candidate_train=1.00,
        candidate_held_out=0.80,
        instruction="…",
    )
    assert train_only.improved is False
    assert train_only.verdict() == "overfitted"

    # --- noise does not produce verdicts --------------------------------------
    assert MIN_IMPROVEMENT > 0, (
        "any improvement, however small, would count — and the metric is not "
        "bit-reproducible, so every run would declare something"
    )
    within_noise = Comparison(
        baseline_train=0.80,
        baseline_held_out=0.80,
        candidate_train=0.80 + MIN_IMPROVEMENT / 2,
        candidate_held_out=0.80 + MIN_IMPROVEMENT / 2,
        instruction="…",
    )
    assert within_noise.verdict() == "unchanged"

    # --- the optimizer is given train only ------------------------------------
    # Asserted against the source rather than trusted. This is the one property
    # the whole criterion rests on, and it is the kind that a refactor breaks
    # silently: passing `held_out` to `compile` would still run, still produce
    # numbers, and quietly measure memorisation.
    from evals import optimize_runner

    source = inspect.getsource(optimize_runner.run_optimization)

    # The arguments to `compile` — the one call that shows the optimizer data.
    # Checking the whole function body would be wrong: `train, held_out = split()`
    # necessarily names both, and an assertion that trips on the unpacking would
    # have to be weakened until it stopped meaning anything.
    compile_args = source.split(".compile(", 1)[1].split("\n    )", 1)[0]
    assert "held_out" not in compile_args, (
        "the held-out set is passed to the optimizer, so the comparison that "
        "follows is not on unseen data and the criterion cannot be satisfied"
    )
    assert "trainset=_as_examples(train)" in compile_args, (
        "the optimizer is not being handed the train split"
    )

    # And the comparison genuinely reads both sets.
    assert "baseline_held_out=_score(baseline, held_out)" in source
    assert "candidate_held_out=_score(candidate, held_out)" in source

    # --- a run is recorded, and recording is not promoting ---------------------
    from evals.optimize import load_report

    report = load_report()
    assert report is not None, (
        "no optimization has ever been recorded, so nothing has been compared on "
        "held-out data in this repository"
    )
    assert report["verdict"] in {"improved", "overfitted", "unchanged"}
    assert report["held_out"] == len(held_out)
    assert "instruction" in report, (
        "the report does not carry the optimized instruction, so nobody can read "
        "what an optimizer proposed before deciding whether to promote it"
    )

    # Promotion is a human act (plans/phase-9.md). The runner must not write a
    # prompt version — an optimizer that promoted its own output would make the
    # library's draft -> candidate -> active lifecycle a formality.
    # Checked as *writes*, not as a mention of the path: the module's own comments
    # reference `prompts/learning_summary/v1.toml` to explain which prompt is
    # being optimized, and an assertion that tripped on prose would push the
    # explanation out of the file to satisfy a test.
    runner_source = inspect.getsource(optimize_runner)
    for write in ("write_text(", "open(", ".write("):
        assert write not in runner_source, (
            f"the optimization runner calls {write} — promotion must stay a "
            "decision a person makes after the evaluation suite agrees, not "
            "something the optimizer does to its own output"
        )
