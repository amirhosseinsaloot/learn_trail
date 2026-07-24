# Phase 6 — Evaluation-driven development

Status: Not started

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> Prompt or model changes cannot be merged without running the evaluation suite.

## Phase test

`tests/phases/test_phase_6.py`

## Tasks

- [ ] Golden conversation, summary, and safety datasets under evals/ (owner: `eval-engineer (not yet created — add per docs/SPEC.md answer when this phase starts)`) — commit: `____`
- [ ] DeepEval pytest-style suite: relevance, faithfulness, completeness, toxicity (owner: `eval-engineer (not yet created)`) — commit: `____`
- [ ] Promptfoo comparisons: prompt A/B, model A/B (owner: `eval-engineer (not yet created)`) — commit: `____`
- [ ] evaluation_case, evaluation_result tables + endpoints (owner: `backend-api`) — commit: `____`
- [ ] CI wiring so the evaluation suite runs on prompt/model-affecting changes (owner: `infra-devops`) — commit: `____`

## Not in this phase

- Red teaming — deferred to Phase 7
- Ragas retrieval evaluation — deferred to Phase 8
- DSPy optimization — deferred to Phase 9
