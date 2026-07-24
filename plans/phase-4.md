# Phase 4 — Safety pipeline

Status: Not started

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> Every model interaction has an explicit, testable safety path.

## Phase test

`tests/phases/test_phase_4.py`

## Tasks

- [ ] NeMo Guardrails: input rail, output rail, jailbreak-detection rail, PII rail (owner: `safety-engineer (not yet created — add per docs/SPEC.md answer when this phase starts)`) — commit: `____`
- [ ] Guardrails AI validators for safety-specific output checks (owner: `safety-engineer (not yet created)`) — commit: `____`
- [ ] Wire input_safety_check / output_safety_check nodes into the main answer graph (owner: `ai-orchestration`) — commit: `____`
- [ ] safety_event table + persistence (owner: `backend-api`) — commit: `____`
- [ ] Block / warning UI for safety decisions (owner: `frontend-web`) — commit: `____`

## Not in this phase

- Observability instrumentation — deferred to Phase 5
- Evaluation-driven development — deferred to Phase 6
- Red teaming — deferred to Phase 7
