# Phase 8 — Search across approved learnings

Status: Not started

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> Answers based on previous learnings identify exactly which approved learning supplied the context.

## Phase test

`tests/phases/test_phase_8.py`

## Tasks

- [ ] Chunking + embedding pipeline for approved learnings via LlamaIndex (owner: `retrieval-engineer (not yet created — add per docs/SPEC.md answer when this phase starts)`) — commit: `____`
- [ ] pgvector migration + hybrid (full-text + semantic) search endpoint (owner: `backend-api`) — commit: `____`
- [ ] Ragas evaluation: retrieval relevance, context recall/precision, answer faithfulness (owner: `retrieval-engineer (not yet created)`) — commit: `____`
- [ ] Ask-across-My-Learnings UI with citations to the source learning (owner: `frontend-web`) — commit: `____`

## Not in this phase

- DSPy prompt optimization — deferred to Phase 9
- Model routing — deferred to Phase 10
