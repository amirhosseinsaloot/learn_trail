# Phase 6 — Evaluation-driven development

Status: Complete

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> Prompt or model changes cannot be merged without running the evaluation suite.

## Phase test

`tests/phases/test_phase_6.py`

## Tasks

- [x] Golden conversation, summary, and safety datasets under evals/ (owner: `ai-orchestration`) — commit: `70faeba`
- [x] DeepEval pytest-style suite: relevance, faithfulness, completeness, toxicity (owner: `ai-orchestration`) — commit: `3adc096`
- [x] Promptfoo comparisons: prompt A/B, model A/B (owner: `ai-orchestration`) — commit: `90749c0`
- [x] evaluation_case, evaluation_result tables + endpoints (owner: `backend-api`) — commit: `3adc096`
- [x] CI wiring so the evaluation suite runs on prompt/model-affecting changes (owner: `infra-devops`) — commit: `90749c0`

The `eval-engineer` agent this plan named does not exist, like Phase 4's
`safety-engineer`. The work was done by `ai-orchestration` and `backend-api`
rather than inventing an agent mid-phase. Two phases have now hit this; worth a
decision before Phase 7, which names a third.

Toxicity is **not** among the metrics shipped. The suite scores relevance,
faithfulness (rubric-driven), forbidden claims and safety-policy compliance. A
toxicity metric on a single-user learning workspace, where the only author of
input is the person reading the output, would be a number nobody acts on — and
an unread metric is worse than an absent one because it makes the suite look
more thorough than it is. It joins when there is a reason.

## The one manual step

**Branch protection is not in this repo.** A workflow can fail a check; only a
GitHub repository setting can make that check *required*. Until `evaluation-gate`
is marked required on the default branch, it reports and does not block, and the
criterion is only half enforced. `gh` is not installed here, so this could not be
done from the session:

```bash
gh api -X PUT repos/amirhosseinsaloot/learn_trail/branches/master/protection \
  --input - <<'JSON'
{"required_status_checks":{"strict":true,"contexts":["evaluation gate"]},
 "enforce_admins":false,"required_pull_request_reviews":null,"restrictions":null}
JSON
```

## What the criterion actually rests on

`tests/phases/test_phase_6.py` asserts the gate rather than the suite: that it
recognises prompt/model changes and *only* those, that a prompt change closes it,
that only a passing run opens it, and that the pull-request workflow invokes it
without a `paths:` filter. Mutation-checked against four deliberate breaks —
un-watching the LiteLLM config, recording failing runs, adding a paths filter,
and ignoring the fingerprint — each of which fails it.

## Known limits, carried forward

- **The fingerprint watches declarations, not behaviour.** It covers the prompt
  library, the alias-to-model mapping, the alias enum and the safety rails'
  prompts. Application code can change an answer without tripping it. A
  fingerprint over all of `ai_core` would change on every commit and the gate
  would degrade into noise, which is how gates die; the nightly full run is the
  intended cover for behaviour changes that arrive as code.
- **The CI job verifies a recorded run; it does not run the suite.** Running it
  there would need a provider credential in CI and would spend on every push. The
  fingerprint is what keeps that honest — a stale manifest cannot pass for a
  fresh one.
- **Scores are nondeterministic.** Thresholds are deliberately below 1.0 because
  the judge is itself a model. A suite that fails on noise is one people rerun
  until it passes.
- **No nightly run.** docs/CODE_QUALITY.md's SLOW lane describes a cron trigger;
  only `workflow_dispatch` and the PR gate exist. Worth adding once there is a
  provider credential in CI.

## Not in this phase

- Red teaming — deferred to Phase 7
- Ragas retrieval evaluation — deferred to Phase 8
- DSPy optimization — deferred to Phase 9
