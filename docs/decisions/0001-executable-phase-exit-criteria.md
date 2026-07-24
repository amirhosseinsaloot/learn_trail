# 0001- Enforce phase discipline via executable exit criteria, not status prose

Status: Accepted

## Context

docs/SPEC.md defines 13 roadmap phases, each with a stated exit criterion (e.g. Phase
1: "You can stop the application, restart it and continue a previous conversation").
The project spans many sessions and, per docs/SPEC.md §7, many narrowly-scoped
subagents. Two failure modes threaten a project shaped like this:

1. A session (human or agent) reads a stale status note, believes a phase is further
   along than it is, and builds Phase N+1 work on top of an incomplete Phase N.
2. A session marks a phase "done" in prose because the code *looks* finished, without
   anything actually checking the exit criterion held.

A markdown status file cannot defend itself against either failure — it will say
whatever it was last told to say, correct or not.

## Decision

Every phase's exit criterion is encoded as a pytest test in `tests/phases/test_phase_N.py`,
marked `@pytest.mark.phase`. These start as hard failures (`pytest.fail("not yet
implemented")`) — never `skip` — so an unbuilt phase reads unambiguously red. `make
status` runs all of them and prints a compact per-phase PASS/FAIL table alongside
`git log` and `git status`, and is the one command any session runs before trusting a
phase-progress claim. `docs/STATE.md` and `plans/phase-N.md` may describe progress in
prose, but that prose is never authoritative — only `make status`'s output is.

Where docs/SPEC.md states no literal exit criterion (Phases 0, 5, 10, 11, 12), the test
docstring says so explicitly and supplies a labeled proxy rather than fabricating a
quote.

## Rejected alternatives

- **A single top-level `PROGRESS.md` checklist, updated by hand.** This is exactly the
  failure mode in Context #1 — nothing forces it to stay accurate, and it degrades
  silently.
- **`skip` markers for unbuilt phases.** A skipped test reads as "not applicable" or
  "fine" in a quick test-run summary, which is indistinguishable at a glance from
  "passing." A hard `fail` cannot be mistaken for success.
- **CI-only enforcement (no local `make status`).** Useful, but doesn't answer "where
  am I" for a session working locally before anything is pushed. `make status` needs to
  work with zero network access and zero CI dependency.

## Revisit if

Once a real evaluation runner exists (Phase 6), phase tests requiring live model calls
(Phases 4, 5, 8+) may need to move behind a marker that separates "fast, offline,
always-run" checks from "slow, model-dependent" ones, so `make status` doesn't become
slow or flaky enough that people stop trusting it.
