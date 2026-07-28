# Phase 4 — Safety pipeline

Status: Complete

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> Every model interaction has an explicit, testable safety path.

## Phase test

`tests/phases/test_phase_4.py`

## Tasks

- [x] NeMo Guardrails: input rail, output rail, jailbreak-detection rail, PII rail (owner: `ai-orchestration`) — commit: `bf0fbdf`
- [x] Guardrails AI validators for safety-specific output checks (owner: `ai-orchestration`) — commit: `bf0fbdf`
- [x] Wire input_safety_check / output_safety_check nodes into the main answer graph (owner: `ai-orchestration`) — commit: `076497f`
- [x] safety_event table + persistence (owner: `backend-api`) — commit: `076497f`
- [x] Block / warning UI for safety decisions (owner: `frontend-web`) — commit: `____`

The plan named a `safety-engineer` agent that does not exist. Rather than invent
one mid-phase, the rails and validators were built by `ai-orchestration`, which
already owns `packages/ai_core`. Worth deciding before Phase 7 (red teaming),
which is the next phase that would want a dedicated safety owner.

## What the criterion actually rests on

`tests/phases/test_phase_4.py` asserts *every* by walking the compiled graph —
every route from START to `generate_answer` passes `input_safety_check`, every
route to `persist` passes `output_safety_check` — rather than by listing paths.
A list is a claim about the graph; a traversal is a fact about it. The test was
mutation-checked against three deliberate breaks (routing a refusal to `persist`,
skipping the input check, recording only refusals); each one fails it.

The summariser — the system's other model call — is covered transitively: its
input is the transcript, and nothing enters the transcript unchecked. That
argument is asserted, not left in a comment.

## Known limits, carried forward

- **The output check runs after tokens stream.** A refused answer will have been
  briefly on screen. Never persisted, and the client is told to discard it.
- **PII detection is regex, not a model.** It finds structured identifiers (keys,
  emails, cards via Luhn, IBANs) and cannot find a name or an address. It warns
  and never blocks — the personal data in a single-user workspace is usually the
  user's own, and refusing to help someone with their own config file would be
  the wrong trade.
- **The rails fail open.** A judge model that is down allows the message through
  with an `allow_with_warning` recorded, rather than taking the product down with
  it. The gap is visible in the audit rather than silently absent.
- **Cost.** A chat request is now three model calls, two of them on the cheap
  alias.

## Not in this phase

- Observability instrumentation — deferred to Phase 5
- Evaluation-driven development — deferred to Phase 6
- Red teaming — deferred to Phase 7
