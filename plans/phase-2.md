# Phase 2 — LangGraph workflow

Status: Not started

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> Each chat request is visible as a deterministic graph execution.

## Phase test

`tests/phases/test_phase_2.py`

## Tasks

- [ ] Build the validate_input -> build_context -> choose_model -> generate_answer -> persist graph (owner: `ai-orchestration`) — commit: `____`
- [ ] Wire LangChain model/message adapters into the graph nodes (owner: `ai-orchestration`) — commit: `____`
- [ ] Add a Postgres checkpointer for graph state (owner: `ai-orchestration`) — commit: `____`
- [ ] Replace the Phase 1 direct call with a call into the graph from the chat endpoint (owner: `backend-api`) — commit: `____`

## Not in this phase

- Structured summary generation — deferred to Phase 3
- Safety pipeline — deferred to Phase 4
- Observability — deferred to Phase 5
