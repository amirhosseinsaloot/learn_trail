# State

Current phase: **Phase 0 — Development environment** (see [plans/phase-0.md](../plans/phase-0.md))

Last completed task: Phase 0 task 3 — `apps/api/` FastAPI skeleton with Ruff and mypy
strict (commit `0c56b7f`). Task 1 (SPEC §16 layout) `1de4a59`; task 2 (uv env)
`1a603eb`.

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

Next task: Add Alembic under `packages/database/` and wire it to the Postgres service —
no models or tables yet, the task ends at an empty runnable migration env — owner
`backend-api`. `packages/database` also has to join the uv workspace `members` list in
the root `pyproject.toml`.

Correction landed 2026-07-25 (commit `7594deb`): `tests/phases/test_phase_5.py` and
`plans/phase-5.md` both wrongly claimed the spec defines no Phase 5 exit criterion and
substituted an invented one. SPEC line 1175 does define one; both now quote it
verbatim. The other PROXY labels (phases 0, 10, 11, 12) were checked and are correct.

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
  The root is a uv workspace aggregator (`package = false`) with one member, `apps/api`.
- Ruff (Tier 1 rule sets, 100 cols) and mypy (strict + Pydantic plugin) are configured
  in the root `pyproject.toml` and **green across the repo** — `ruff check`,
  `ruff format --check`, and `mypy .` all exit 0.
- `apps/api/` — `learntrail-api`, a hatchling distribution exposing top-level `api`.
  `api.main:app` is a FastAPI app object with **no routes**; only FastAPI's built-in
  `/openapi.json`, `/docs`, `/redoc` exist. Runtime deps: fastapi, pydantic, uvicorn.
- All 13 `tests/phases/test_phase_*.py` still fail on purpose.
- Still no database code, no frontend code, no `docker-compose.yml`.

---

Written by a model. Verify with `make status` before acting on anything above — this
file is a claim, not a fact.
