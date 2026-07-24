# Phase 10 — Model routing

Status: Not started

## Exit criterion

PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this phase:

> A request through the difficulty classifier is routed to the cheap-model path for a simple question and the strong-model path for a difficult one, and a forced timeout triggers the documented fallback strategy.

## Phase test

`tests/phases/test_phase_10.py`

## Tasks

- [ ] Difficulty classifier + LangGraph conditional edges for cheap/strong model paths (owner: `ai-orchestration`) — commit: `____`
- [ ] LiteLLM routing, fallback, and timeout configuration; cost budget enforcement (owner: `infra-devops`) — commit: `____`
- [ ] Model-comparison dashboard (owner: `frontend-web`) — commit: `____`

## Not in this phase

- Local models — deferred to Phase 11
- Advanced learning features — deferred to Phase 12
