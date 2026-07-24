---
description: End the session — verify status, overwrite docs/STATE.md, tick off completed plan tasks, and prompt for an ADR if warranted.
---

Close out this session. Follow these steps in order — do not skip the verification
step, and do not write anything to a file based on memory of what you *intended* to do
this session rather than what actually happened.

1. **Run `make status`.** This is the only source of truth for phase pass/fail state
   and for what's actually committed (`git log`, `git status`). Read its output before
   writing anything below. If it disagrees with your memory of the session, trust it.

2. **Overwrite `docs/STATE.md`** (replace the whole file — never append):
   - Current phase, derived from `make status`'s PASS/FAIL table, not from what phase
     you were "trying to work on."
   - Last completed task and next task, in concrete terms someone with zero context
     could act on.
   - "In-flight / half-done": anything git can't show on its own — unapplied
     migrations, a stubbed endpoint returning 501, a flaky test, a half-renamed
     symbol. Say "none" if there's genuinely nothing, don't invent filler.
   - If you are not sure about any of the above, write **"unknown"** — do not guess to
     fill the section in.
   - Keep the closing line: written by a model, verify with `make status` before
     acting on it.

3. **Update the active phase's plan file** (`plans/phase-N.md` for the current phase
   per `make status`):
   - Tick `- [ ]` to `- [x]` only for tasks you can confirm are done (the code exists,
     and — for anything a phase test covers — the relevant assertion passes).
   - Fill in the commit hash for each newly-ticked task from `git log`. If a task was
     completed across multiple commits, list the last one that finished it.
   - Do not tick a task on the strength of "I wrote most of it" — partially-done work
     belongs in STATE.md's in-flight section, not a checked box.

4. **Ask about an ADR.** If this session made a non-obvious decision — chose one
   approach over a plausible alternative, deviated from `docs/SPEC.md`, or made a
   choice future sessions might question — ask the user whether it should be recorded
   in `docs/decisions/` using `docs/decisions/TEMPLATE.md`. Don't write the ADR
   unprompted; don't skip asking just because it's extra work.

Report back with: the `make status` table, what you changed in STATE.md and the plan
file, and whether an ADR was written.
