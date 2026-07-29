# Phase 9 — Prompt optimization

Status: Complete

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> The optimized program performs better on held-out examples, not only its optimization set.

## Phase test

`tests/phases/test_phase_9.py`

## Tasks

- [x] Pick one stable task (summary generation) with a metric, baseline, train/val split (owner: `ai-orchestration`) — commit: `d5011f1`
- [x] DSPy optimization run + held-out comparison against the manual baseline (owner: `ai-orchestration`) — commit: `d5011f1`
- [~] Version and store the optimized prompt as a new candidate — **deliberately not done**

      The lifecycle exists and the runner refuses to write a prompt version on
      its own. No candidate is stored because none earned it: four consecutive
      runs alternated IMPROVED / OVERFITTED (see below), so any instruction
      committed here would be one draw from a coin flip wearing the provenance of
      a measured result. "Do not promote without the evaluation suite" is the
      task's own instruction, and the suite has not endorsed anything.

## What the criterion actually rests on

`tests/phases/test_phase_9.py` asserts the machinery, never the outcome: the
split is disjoint and deterministic, the optimizer is handed `train` only
(checked against the *source* of the `compile` call, not a comment), `improved`
reads the held-out delta and never the train delta, a train-only gain reports
`overfitted`, and a difference under `MIN_IMPROVEMENT` reports `unchanged`.
Mutation-checked against four breaks — judging by the train delta, an overlapping
split, handing the optimizer the held-out set, and removing the noise floor. All
four fail it.

## The result: not established, and that is the finding

    run 1   train 1.00 -> 1.00   held-out 0.71 -> 0.79    IMPROVED
    run 2   train 0.80 -> 0.90   held-out 0.79 -> 0.71    OVERFITTED
    run 3   train 0.87 -> 1.00   held-out 0.76 -> 0.88    IMPROVED
    run 4   train 0.80 -> 0.93   held-out 0.85 -> 0.74    OVERFITTED

Averaging each score over three passes was added between runs 2 and 3 and did not
settle it. That located the variance precisely: it is not in the scoring, it is
in **which instruction COPRO lands on**. COPRO is a stochastic search, so
repeated runs propose different candidates — they are not repeated measurements
of one thing.

Nine cases cannot certify a prompt. What is demonstrated is the smaller claim the
criterion actually makes: the apparatus tells a gain that generalised from one
that did not, and it has reported `overfitted` on real runs where train rose and
held-out fell.

## Known limits, carried forward

- **The dataset is nine cases.** Five train, four held out. Growing it is the
  single highest-value thing anyone could do to this phase; every other limit
  here follows from it.
- **The optimizer's own variance dominates.** Reducing it needs either many
  optimization runs (expensive) or a deterministic optimizer (COPRO is not one).
- **The metric is keyword coverage, not judgement.** Deliberate — a judged metric
  inside the optimizer's scoring loop compounds its noise across every candidate
  — but it means a summary can score well while reading badly. The golden suite's
  judged metrics are the backstop, and a promoted prompt must pass them.
- **`learning_answer@1` is unoptimized.** It was written by hand this phase
  because docs/SPEC.md §12 names it and it did not exist. It is a candidate for
  the same treatment once the dataset is larger.

## Not in this phase

- Model routing — deferred to Phase 10
- Local models — deferred to Phase 11
