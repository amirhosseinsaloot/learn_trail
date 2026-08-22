# Phase 12 — Advanced learning features

Status: Complete

## Exit criterion

PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this phase:

> At least one advanced learning feature (quiz generation, flashcards, spaced repetition, knowledge graph, learning-path recommendations, document ingestion, voice interface, MCP-based tools, or Markdown/PDF export) is implemented and covered by its own passing test.

## Phase test

`tests/phases/test_phase_12.py`

## Tasks

- [x] Flashcard generation from an approved Learning: schema, prompt, agent, endpoint, UI (owner: `ai-orchestration / backend-api / frontend-web`) — commit: `e136c4a`

## What was built, and why this one

Flashcard generation from an approved Learning. Of the nine features docs/SPEC.md
§15 lists, this is the one that exercises the whole platform a final time — the
gateway alias, pydantic-ai typed generation, Pydantic validation, an endpoint and
a UI — which is a fitting thing for the last phase to demonstrate rather than a
feature that sits to one side of everything built so far.

A flashcard set is study material derived from knowledge, not knowledge. So it is
generated on demand and never stored: no table, no approval gate, no migration.
`POST /learnings/{id}/flashcards` renders the Learning, generates a validated set,
and returns it; the UI flips cards on click. A deleted or missing Learning is
refused — flashcards come from the library, not from anything.

## What the criterion actually rests on

`tests/phases/test_phase_12.py` asserts the feature end to end with the model
stubbed: the schema rejects a degenerate set, the endpoint generates from an
approved Learning and names its id, and it refuses a deleted (409) or missing
(404) one. Mutation-checked against two breaks — the schema no longer rejecting a
self-restating card, the endpoint no longer refusing a deleted Learning; each
fails it. Live, six valid cards were generated from a real Learning, every one
answerable from it.

## Known limits, carried forward

- **Cards are not persisted.** Deliberate — they are a study aid, not knowledge —
  but it means no review history and no spaced-repetition scheduling. Spaced
  repetition is the natural follow-on and would need the table this feature
  avoided.
- **Quality rests on the prompt, not an evaluation.** Unlike the summary path,
  flashcards have no golden set in the Phase 6 suite. The schema catches
  degenerate structure; it does not catch a card that is well-formed but a poor
  question. A flashcard dataset is the obvious next addition.

## Not in this phase

- Anything beyond docs/SPEC.md — this is the last defined roadmap phase
