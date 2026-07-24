# Phase 3 — Structured summary generation

Status: Not started

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> Malformed or incomplete summaries are rejected before persistence.

## Phase test

`tests/phases/test_phase_3.py`

## Tasks

- [ ] Author and version the learning_summary prompt (owner: `prompt-librarian`) — commit: `____`
- [ ] Pydantic AI summary-generation task with the LearningSummary schema (docs/SPEC.md §7) (owner: `ai-orchestration`) — commit: `____`
- [ ] Add Guardrails AI schema validators + LangGraph approval interrupt to the summary graph (owner: `ai-orchestration`) — commit: `____`
- [ ] summary_draft, learning, learning_revision tables + endpoints (edit/regenerate/approve) (owner: `backend-api`) — commit: `____`
- [ ] Summary review UI: edit, regenerate, approve; My Learnings + revision history views (owner: `frontend-web`) — commit: `____`

## Not in this phase

- NeMo Guardrails / provider moderation / PII rails — deferred to Phase 4
- Observability instrumentation — deferred to Phase 5
- Evaluation suite — deferred to Phase 6
- Retrieval over approved learnings — deferred to Phase 8
