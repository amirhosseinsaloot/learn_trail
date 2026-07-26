# State

Current phase: **Phase 0 is COMPLETE. Phase 1 — Basic AI chat is next** (see
[plans/phase-1.md](../plans/phase-1.md)); nothing in Phase 1 has been started.

`make status` reports **Phase 0 PASS** — the first phase to go green. Phases 1–12
are red, as designed.

Last completed task: Phase 0 task 9 — the real `tests/phases/test_phase_0.py`
(commit `872bcb5`). Earlier: task 1 (SPEC §16 layout) `1de4a59`, task 2 (uv env)
`1a603eb`, task 3 (FastAPI skeleton + Ruff + mypy) `0c56b7f`, task 4 (Alembic env)
`2b0e933`, task 5 (pytest discovery) `06b9736`, task 6 (Next.js skeleton) `6132a66`,
task 7 (lefthook + make targets) `600d919`, task 8 (docker-compose) `e7bed57`.

Next task: the first Phase 1 task in [plans/phase-1.md](../plans/phase-1.md). Read
the notes carried onto its LiteLLM-in-compose and chat-page tasks before starting
either — they record what Phase 0 deliberately left undone for Phase 1 to do
(`.env` and gitleaks arriving with the first real credential, the
`frontend`→`backend` dependency, and the fact that adding a compose service
**requires** widening `PHASE_0_SERVICES` in `tests/phases/test_phase_0.py` in the
same commit or Phase 0 flips to FAIL).

Phase 0 exit criterion, verified by running it: `make up` brings postgres, backend
and frontend to `healthy`; `alembic upgrade head` runs from inside the backend
container; host ports 5432, 8000 and 3000 all answer.

## In-flight / half-done

Nothing in-flight. This section exists for work `git log`/`git status` can't show on
their own — unapplied migrations, endpoints stubbed to return 501, flaky tests, a
half-renamed function.

One thing worth knowing that git cannot show: the Docker **images are built and the
stack may still be running** on this machine. `make ps` says which. `make down`
stops it and keeps the `postgres_data` volume; `docker compose down -v` is the
explicit throw-the-data-away gesture. The database has zero tables — Alembic has
zero revisions until Phase 1.

## What exists right now

- `docs/SPEC.md` — the full product/architecture spec.
- `CLAUDE.md` — cross-phase invariants.
- `.claude/agents/` — six subagents for Phase 0–3 boundaries (`backend-api`,
  `frontend-web`, `ai-orchestration`, `infra-devops`, `prompt-librarian`,
  `architecture-reviewer`). The Phase 4+ agents named in the subagent design
  (`safety-engineer`, `observability-engineer`, `eval-engineer`, `red-team`,
  `retrieval-engineer`, `prompt-optimizer`) do not exist yet — add each when its phase
  starts.
- `tests/phases/test_phase_0.py` — **real**, and green. `test_phase_1.py` …
  `test_phase_12.py` are still intentionally failing placeholders.
- `plans/phase-0.md` … `phase-12.md` — task breakdown per phase.
- `docs/decisions/` — ADR template + 0001 (why exit criteria are executable).
- The SPEC §16 directory tree (`apps/`, `packages/`, `tests/`, `prompts/`, `infra/`).
  `packages/ai_core/prompts/` is deliberately absent — top-level `prompts/` is
  canonical. `packages/ai_core/` and `packages/evals/` are still `.gitkeep`-only and
  are not yet uv workspace members (ai_core joins in Phase 1, evals in Phase 6).
- Root `pyproject.toml` + committed `uv.lock` + `.python-version` (3.12) + `README.md`.
  `uv sync --all-groups` builds `.venv/` with pytest 9.1.1, ruff 0.16.0, mypy 2.3.0.
  The root is a uv workspace aggregator (`package = false`) with two members,
  `apps/api` and `packages/database`.
- Ruff (Tier 1 rule sets, 100 cols) and mypy (strict + Pydantic plugin) are configured
  in the root `pyproject.toml` and **green across the repo**.
- `apps/api/` — `learntrail-api`, a hatchling distribution exposing top-level `api`.
  `api.main:app` is a FastAPI app object with **no routes**; only FastAPI's built-in
  `/openapi.json`, `/docs`, `/redoc` exist. Runtime deps: fastapi, pydantic, uvicorn.
- `packages/database/` — `learntrail-database`, exposing top-level `database`. Empty
  `Base` (zero tables) with a constraint naming convention, `database_url()` reading
  `DATABASE_URL`, and a runnable Alembic env at `packages/database/alembic.ini` with
  **zero revisions**. Driver: psycopg 3. Deps: alembic, psycopg[binary], sqlalchemy.
- One root `pytest.ini` discovering `tests/`, `apps/` and `packages/` under
  `--import-mode=importlib`. `pytest` from the root: **12 failed, 10 passed** — the 12
  remaining phase placeholders are red on purpose; the 8 unit tests in
  `apps/api/tests/` and `packages/database/tests/` plus the 2 real Phase 0 phase tests
  pass. Which of the four test homes a new test belongs in is written down in
  [CLAUDE.md](../CLAUDE.md).
- A pnpm workspace at the root (`package.json`, `pnpm-workspace.yaml`, committed
  `pnpm-lock.yaml`, `biome.jsonc`) with one member, `apps/web`. Biome lives at the root;
  Next/React/TS/ESLint in `apps/web`.
- `apps/web/` — Next.js App Router + React + Tailwind, one static landing page, no
  fetch and no `.env`. Biome (format + fast lint), typescript-eslint (type-aware rules
  only) + `@next/eslint-plugin-next`, `tsc --noEmit` with `strict`,
  `noUncheckedIndexedAccess` and `allowJs: false`. `biome ci`, `eslint`, `typecheck` and
  the production build all pass.
- Frontend commands: root `pnpm run lint:web` / `type:web`; in `apps/web`, `dev`,
  `build`, `lint`, `typecheck` (= `next typegen && tsc --noEmit` — the prefix is
  load-bearing, the tsconfig includes generated files).
- `lefthook.yml` + installed `.git/hooks`. pre-commit (~0.1s) autofixes and re-stages
  staged files; pre-push (~5s) runs `make lint-py type-py type-web lint-web test`.
  gitleaks is wired but inert until Phase 1. `make help` lists every target;
  `make fast` runs the whole Phase 0 check set.
- `docker-compose.yml` + `.dockerignore` + `infra/docker/{backend,frontend}.Dockerfile`
  — **exactly three services**, each with a real healthcheck: `postgres` (18-alpine,
  5432 published, named `postgres_data` volume), `backend` (uvicorn `--reload` on
  bind-mounted source, venv at `/opt/venv` outside `/app`, 8000 published), `frontend`
  (`next dev`, anonymous volumes over `node_modules` and `.next`, 3000 published).
  Both images are development images running as uid 1000; production stages land when
  there is something to deploy. Driven by `make up` / `down` / `logs` / `ps`.
- **No CI.** Hooks and `make fast` are the only enforcement, and both are bypassable
  with `--no-verify`. The FAST CI lane moved to Phase 1.

---

Written by a model. Verify with `make status` before acting on anything above — this
file is a claim, not a fact.
