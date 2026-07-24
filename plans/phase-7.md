# Phase 7 — Red teaming

Status: Not started

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> You can measure whether a safety change improves or harms the system.

## Phase test

`tests/phases/test_phase_7.py`

## Tasks

- [ ] Adversarial dataset under evals/red_team/: injection, jailbreak, PII leakage, system-prompt extraction, multi-turn bypass (owner: `red-team (not yet created — add per docs/SPEC.md answer when this phase starts)`) — commit: `____`
- [ ] Promptfoo red-team suite + attack-success-rate reporting (owner: `red-team (not yet created)`) — commit: `____`
- [ ] CI safety gate that blocks merges on red-team regressions (owner: `infra-devops`) — commit: `____`

## Not in this phase

- Retrieval / Ragas — deferred to Phase 8
- Prompt optimization — deferred to Phase 9
