# State

Current phase: **Phase 0 — Development environment** (see [plans/phase-0.md](../plans/phase-0.md))

Last completed task: Phase 0 task 2 — uv-managed root Python env with a committed
`uv.lock` (commit `1a603eb`). Task 1 (SPEC §16 layout) was `1de4a59`.

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
lefthook).

Both CODE_QUALITY.md open calls are now resolved (2026-07-25, commit `181a0e6`):
`@next/eslint-plugin-next` is allowed as the single non-type-aware ESLint exception,
and Zod is scoped to purely-local form state only (never API shapes — those come from
openapi-typescript in Phase 1). Neither adds a Phase 0 dependency beyond the ESLint
plugin.

Next task: Scaffold `apps/api/` FastAPI skeleton (no routes yet) with Ruff rule sets
and mypy strict + Pydantic plugin — owner `backend-api`. Two watch items recorded at
the bottom of plans/phase-0.md apply to it (mypy 2.x plugin compatibility must be
verified by running it, not assumed; pytest 9 import-mode collisions).

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
- The SPEC §16 directory tree (`apps/`, `packages/`, `tests/`, `prompts/`, `infra/`),
  every leaf holding only a `.gitkeep`. `packages/ai_core/prompts/` is deliberately
  absent — top-level `prompts/` is canonical.
- Root `pyproject.toml` + committed `uv.lock` + `.python-version` (3.12) + `README.md`.
  `uv sync --all-groups` builds `.venv/` with pytest 9.1.1, ruff 0.16.0, mypy 2.3.0.
  Ruff and mypy are installed but deliberately **unconfigured** — their settings land
  with the code they check.
- Still no application code, no per-app manifests, no `docker-compose.yml`.

---

Written by a model. Verify with `make status` before acting on anything above — this
file is a claim, not a fact.
