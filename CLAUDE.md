# LearnTrail

Single-user AI learning workspace: persistent Q&A conversations distilled into
human-approved "Learnings," built incrementally across 13 phases. Full spec: [docs/SPEC.md](docs/SPEC.md).

## Invariants (hold in every phase)

1. No auth, no users. No `user` table, no `user_id` column, ever.
2. Every model call goes through a LiteLLM alias (`learning-fast`, `learning-deep`,
   `safety-judge`) — never a hard-coded provider/model string.
3. Model-provider credentials are server-side only. The frontend never sees them and
   never calls a model API directly.
4. Every structured model output is parsed through a Pydantic schema before it touches
   persistence or a response. Reject or retry on validation failure — never loosen
   validation to make bad data fit.
5. Nothing becomes an approved Learning — created, edited, deleted, or merged —
   without an explicit human approval action. The model may draft; it may never promote.
6. One new AI concept per phase. Don't introduce a framework, safety layer, or
   evaluation tool ahead of the roadmap phase that calls for it.

## Before trusting any status claim

Markdown is not the source of truth for what is done — code and git are. Run
`make status` before believing anything in [docs/STATE.md](docs/STATE.md) about
current phase or progress.

## Where things live

- [docs/STATE.md](docs/STATE.md) — current phase, last/next task, in-flight work
- [plans/](plans/) — one file per phase: tasks, exit criterion, what's deferred
- [docs/decisions/](docs/decisions/) — ADRs for non-obvious decisions
- [tests/phases/](tests/phases/) — executable exit criteria, one per phase

Where a test goes:

- `tests/phases/` — exit criteria, one file per phase. Nothing else.
- `<member>/tests/` (e.g. `apps/api/tests/`, `packages/database/tests/`) — unit tests
  scoped to one workspace member, travelling with the package they test.
- `tests/{integration,ai,safety,end_to_end}/` — suites that span more than one member.
- `tests/unit/` — cross-package pure-logic tests only. If a test names a single member,
  it belongs in that member's `tests/` instead.
