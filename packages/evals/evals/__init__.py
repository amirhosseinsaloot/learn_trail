"""Evaluation for LearnTrail (docs/SPEC.md §9-10, Phase 6).

Three separable pieces, and the separation is deliberate:

- `datasets` — the golden cases, as data. No model, no network.
- `gate` — what makes Phase 6's exit criterion enforceable: which changes
  require an evaluation run, and whether one has happened since. No model.
- `suites` — the DeepEval tests that actually score answers. These call models
  and cost money, and are the only part that does.

Only the third needs the `judges` extra installed. A clean checkout can run the
gate, which is the half that has to work on every commit.
"""
