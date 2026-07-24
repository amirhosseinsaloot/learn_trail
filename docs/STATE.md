# State

Current phase: **Phase 0 — Development environment** (see [plans/phase-0.md](../plans/phase-0.md))

Last completed task: None. Repo scaffolding (spec, invariants, subagents, phase tests,
plans, ADRs, session-continuity tooling) was just created; no Phase 0 build task is
checked off yet.

Plan audit (2026-07-24): before starting the build, the Phase 0 plan was amended —
Phase 0's compose/exit criterion narrowed to Postgres + backend + frontend (services
join docker-compose in the phase that introduces their concept; LiteLLM → Phase 1,
Phoenix → Phase 5), compose task moved after the app skeletons, Alembic pinned to
packages/database/, single root pytest config, top-level prompts/ made the single
canonical prompts dir, and `make status` now prefers `.venv/bin/python`.

Tooling track (2026-07-24, planning only — nothing installed): docs/CODE_QUALITY.md
defines the phased code-quality toolchain (tiers, either/or decisions, FAST/SLOW CI
lanes, import-linter contracts, per-phase checklist); docs/ROADMAP_TOOLING.md maps
tools onto the §15 phases without editing the spec. plans/phase-0.md now carries the
Phase 0 tooling tasks (uv, Ruff, mypy-only, Biome, typescript-eslint, tsc strict,
lefthook). Two open calls for the user are flagged at the bottom of CODE_QUALITY.md
(Zod scope; Next.js ESLint plugin exception).

Next task: Scaffold the monorepo layout (`apps/web/`, `apps/api/`, `packages/`,
`infra/`) per `plans/phase-0.md`'s task list — owner `infra-devops`.

## In-flight / half-done

Nothing in-flight. This section exists for work `git log`/`git status` can't show on
their own — unapplied migrations, endpoints stubbed to return 501, flaky tests, a
half-renamed function. Nothing like that exists yet because no application code exists
yet.

## What exists right now

- `docs/SPEC.md` — the full product/architecture spec.
- `CLAUDE.md` — cross-phase invariants.
- `.claude/agents/` — six subagents for Phase 0–3 boundaries (`backend-api`,
  `frontend-web`, `ai-orchestration`, `infra-devops`, `prompt-librarian`,
  `architecture-reviewer`). The Phase 4+ agents named in the subagent design
  (`safety-engineer`, `observability-engineer`, `eval-engineer`, `red-team`,
  `retrieval-engineer`, `prompt-optimizer`) do not exist yet — add each when its phase
  starts.
- `tests/phases/test_phase_0.py` … `test_phase_12.py` — all intentionally failing
  placeholders.
- `plans/phase-0.md` … `phase-12.md` — task breakdown per phase.
- `docs/decisions/` — ADR template + 0001 (why exit criteria are executable).
- No application code: no `apps/`, no `packages/`, no `docker-compose.yml`.

---

Written by a model. Verify with `make status` before acting on anything above — this
file is a claim, not a fact.
