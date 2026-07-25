# Phase 5 — Observability

Status: Not started

## Exit criterion

Verbatim, docs/SPEC.md:

> A poor answer can be traced through context construction, model execution, guardrails and persistence.

How this will be asserted: a chat request emits a trace containing the expected span
names (`chat.request`, `load_conversation`, `input_guardrails`, `context_builder`,
`llm.generate`, `output_guardrails`, `persist_message`) — the four stages the criterion
names, made observable. That span list is an implementation choice, not the criterion.

## Phase test

`tests/phases/test_phase_5.py`

## Tasks

- [ ] Deploy Phoenix and an OTel collector in docker-compose.yml (owner: `infra-devops`) — commit: `____`
- [ ] OpenTelemetry + OpenInference instrumentation on graph nodes, guardrail checks, model calls (owner: `ai-orchestration`) — commit: `____`
- [ ] Record trace_id, prompt_version, model_alias, tokens, cost, latency onto model_run (owner: `backend-api`) — commit: `____`
- [ ] Trace-link UI from a chat/message back to its Phoenix trace (owner: `frontend-web`) — commit: `____`

## Not in this phase

- Evaluation-driven development — deferred to Phase 6
- Red teaming — deferred to Phase 7
- Permanent Langfuse deployment (comparison-only, not a second production backend) — deferred to Phase 5
