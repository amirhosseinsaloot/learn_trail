# Phase 9 — Prompt optimization

Status: Not started

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> The optimized program performs better on held-out examples, not only its optimization set.

## Phase test

`tests/phases/test_phase_9.py`

## Tasks

- [ ] Pick one stable task (recommended: summary generation) with a metric, baseline, train/val split (owner: `prompt-optimizer (not yet created — add per docs/SPEC.md answer when this phase starts)`) — commit: `____`
- [ ] DSPy optimization run + held-out comparison against the manual baseline (owner: `prompt-optimizer (not yet created)`) — commit: `____`
- [ ] Version and store the optimized prompt as a new candidate; do not promote without the evaluation suite (owner: `prompt-librarian`) — commit: `____`

## Not in this phase

- Model routing — deferred to Phase 10
- Local models — deferred to Phase 11
