# Phase 5 — Observability

Status: Complete

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

- [x] Deploy Phoenix in docker-compose.yml (owner: `infra-devops`) — commit: `16e0d88`
      The standalone OTel collector this task originally named was dropped; see
      [ADR 0002](../docs/decisions/0002-no-otel-collector.md). SPEC §6's service
      list does not include one, and vendor-neutrality comes from instrumenting
      with the OTel SDK rather than from running a forwarder.
- [x] OpenTelemetry + OpenInference instrumentation on graph nodes, guardrail checks, model calls (owner: `ai-orchestration`) — commit: `3bc6585`
- [x] Record trace_id, prompt_version, model_alias, tokens, cost, latency onto model_run (owner: `backend-api`) — commit: `6400b24`
- [x] Trace-link UI from a chat/message back to its Phoenix trace (owner: `frontend-web`) — commit: `c63e75c`

## What the criterion actually rests on

`tests/phases/test_phase_5.py` reads `CRITERION_STAGES` — the map from the
criterion's four words to the spans that make each visible — rather than a copy
of the span list, so the instrumentation and the criterion cannot drift apart. It
was mutation-checked against three deliberate breaks; two failed it, and the
third (removing the explicit error-status handler) *passed*, which revealed the
handler was redundant with `start_as_current_span`'s own defaults. It is now a
comment explaining its own absence.

The endpoint half of the trace — `load_conversation`, and the nesting of every
graph span under one `chat.request` — is asserted by `apps/api/tests/test_tracing.py`
against the real app. The phase test covers the graph half without an HTTP client
or a database, and the split is deliberate: between them they cover the whole
sentence, and `make status` stays fast and model-free.

## Known limits, carried forward

- **The graph does not open its own root span.** Its nodes nest under whatever is
  current, so trace coherence comes from the caller. The endpoint opens
  `chat.request`; a first draft of the phase test did not, and produced five
  separate traces for one answer. Anything that invokes the graph directly must
  open a root or get a disconnected trace.
- **Prices are a local table.** `estimated_cost` is an estimate and says so in
  its name: `ai_core/models/pricing.py` will drift from the provider's real bill
  the moment prices change, and it knows nothing about cached-input discounts. An
  unpriced model records `None`, never `0`.
- **`prompt_version` on `model_run` is always NULL for the chat path.** The chat
  answer has no prompt version until the prompt library covers it; the column is
  recorded as absent rather than given an invented default. The summary path's
  `summary_draft.model_run_id` is likewise present in the schema but not yet
  written — the summariser is not instrumented in this phase.
- **Trace retention is unbounded.** Phoenix keeps everything on its volume, and
  nothing prunes it.

## Not in this phase

- Evaluation-driven development — deferred to Phase 6
- Red teaming — deferred to Phase 7
- Permanent Langfuse deployment (comparison-only, not a second production backend) — deferred to Phase 5
