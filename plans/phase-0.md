# Phase 0 — Development environment

Status: CURRENT PHASE

## Exit criterion

PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this phase:

> Every service docker-compose.yml defines in Phase 0 (Postgres, backend, frontend)
> reports a healthy status.

Phoenix and LiteLLM Proxy are **not** part of this criterion. Per invariant #6, a
service joins docker-compose.yml in the phase that introduces its concept: LiteLLM
Proxy in Phase 1, Phoenix (+ OTel collector) in Phase 5. SPEC §6's five-service list
describes the end state, not Phase 0.

## Phase test

`tests/phases/test_phase_0.py`

Semantics (so `make status` stays trustworthy): the test must distinguish
"environment not running" from "phase not built". It statically validates
`docker compose config` (services exist, each defines a healthcheck), and only
asserts live health via `docker compose ps` when the Docker daemon is reachable.
If Docker is down it fails with an explicit "docker not running — run
`docker compose up -d`" message, never a generic assertion error.

## Tasks

Ordering note: docker-compose.yml is written **last** — its backend/frontend services
reference Dockerfiles that only exist after the app skeletons land.

- [x] Scaffold the monorepo layout from docs/SPEC.md §16 (apps/, packages/, tests/,
      prompts/, infra/), with `.gitkeep` in each empty directory so git tracks it.
      Do not create `packages/ai_core/prompts/` — top-level `prompts/` is the single
      canonical prompts directory (prompt text is lifecycle-managed content owned by
      `prompt-librarian`, loaded as files, never imported as Python source)
      (owner: `infra-devops`) — commit: `1de4a59`
- [x] Root Python env managed by uv with a committed `uv.lock`; dev tooling (pytest,
      Ruff, mypy) installable via one documented command; `make status` uses
      `.venv/bin/python` when present (owner: `infra-devops`) — commit: `1a603eb`
- [x] Scaffold apps/api/ FastAPI app skeleton (no routes yet) with Ruff
      (lint + format, rule sets per docs/CODE_QUALITY.md) and mypy strict +
      Pydantic plugin — mypy only, no Pyright (docs/CODE_QUALITY.md
      "Decisions and rejections") (owner: `backend-api`) — commit: `0c56b7f`
- [x] Add Alembic under packages/database/ and wire it to the Postgres service.
      No models/tables yet — Phase 1 adds `chat`/`message`; this task ends at an
      empty, runnable migration env (owner: `backend-api`) — commit: `2b0e933`
- [x] Extend the root pytest.ini so apps/api/ and packages/database/ tests are
      discovered — single root config, no per-package pytest configs
      (owner: `backend-api`) — commit: `06b9736`
- [x] Scaffold apps/web/ Next.js + TypeScript + Tailwind skeleton with Biome
      (format + fast lint), typescript-eslint (type-aware rules only), and
      `tsc --noEmit` with `strict` + `noUncheckedIndexedAccess`
      (owner: `frontend-web`) — commit: `6132a66`
- [x] lefthook root config: pre-commit (ruff, biome, gitleaks-ready), pre-push
      (mypy, tsc, unit tests); plus `make` targets so every check runs locally
      with one command (owner: `infra-devops`) — commit: `600d919`
      - The `lefthook` npm package fetches its Go binary via an install script,
        and pnpm 10+ blocks those by default. Expect `pnpm add -D -w lefthook` to
        leave no working binary until it is added to the allowed-builds list in
        `pnpm-workspace.yaml`.
      - Script names task 6 established, to wire up rather than reinvent: root
        `pnpm run lint:web` (= `biome ci . && eslint .`) and `pnpm run type:web`;
        in `apps/web`, `lint`, `typecheck`, `build`, `dev`.
      - `biome` resolves only from the **root** `node_modules/.bin`, not
        `apps/web`'s. Invoke Biome from the repo root; ESLint and tsc via
        `pnpm --filter web`.
      - `typecheck` is `next typegen && tsc --noEmit`, not bare `tsc`: the
        tsconfig includes generated, gitignored files, so bare `tsc` fails on a
        clean checkout. Do not "simplify" it.
- [ ] Write docker-compose.yml: Postgres, backend, frontend — each with a healthcheck
      (owner: `infra-devops`) — commit: `____`
      - Postgres contract, fixed by task 4 (`packages/database/database/config.py`):
        role `learntrail`, password `learntrail`, database `learntrail`, container
        port 5432 published on host 5432. Compose must pass the backend
        `DATABASE_URL=postgresql+psycopg://learntrail:learntrail@postgres:5432/learntrail`
        — service name, not `localhost`. The `+psycopg` is load-bearing: a bare
        `postgresql://` URL resolves to psycopg2, which is deliberately not a
        dependency, and fails at import.
      - **Packaging trap:** `packages/database`'s wheel ships only the `database/`
        package, so `alembic.ini` and `migrations/` are *not* in the built
        distribution. An image built by installing the wheel gets an importable
        `database` but no migration env, and `alembic upgrade head` fails with
        "path doesn't exist". Either `COPY packages/database/` in as source, or
        move migrations under `database/` so they ship with the wheel.
      - Backend healthcheck target: `apps/api` has no routes by design, so use
        FastAPI's built-in `/openapi.json`. Do **not** add a health endpoint —
        routes are Phase 1.
      - Frontend contract, fixed by task 6: port 3000, dev command
        `pnpm --filter web dev`, healthcheck `GET http://localhost:3000/` → 200
        (the page is static, so the frontend can be healthy independently of the
        backend). Build context must be the **repo root**, not `apps/web` —
        `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml` and `biome.jsonc`
        all live there and `pnpm install --frozen-lockfile` needs them. There is
        no `.dockerignore` yet; without one, `COPY` drags in `node_modules/`,
        `.next/` and `.venv/`. Do not bind-mount over `node_modules` (pnpm
        symlink farm) — use anonymous volumes.
- [ ] Replace the placeholder tests/phases/test_phase_0.py with the executable exit
      criterion described above (owner: `backend-api`) — commit: `____`

## Watch items surfaced during the build

- **mypy 2.x + Pydantic plugin — RESOLVED in task 3.** The lock resolved mypy 2.3.0,
  a major past what docs/CODE_QUALITY.md was written against, and mypy has no stable
  plugin API. Verified by running `mypy --strict` over a trivial `BaseModel` and
  confirming both `init_typed` (wrong field type → `arg-type`) and `init_forbid_extra`
  (unknown kwarg → `call-arg`) actually fire. No pin-back needed. There is no config
  flag that makes a silently-missing plugin fatal, so **repeat this check by hand on
  the next mypy major**; if it ever breaks, pin mypy back rather than dropping the
  plugin (it is why mypy was chosen over Pyright) or adding a second checker.
- **pytest 9 import mode — RESOLVED in task 5.** Same-named test modules across the
  three trees collide under the default `prepend` mode. Fixed with
  `addopts = --import-mode=importlib`. Note it must go through `addopts`: there is no
  `importmode` ini key, and writing one is accepted with a `PytestConfigWarning` and
  silently does nothing — so "tidying" it into an ini key would quietly reintroduce
  the collision.
- **`norecursedirs` is unset on purpose** (task 5). pytest's default already prunes
  `node_modules`, and setting the key replaces the default rather than extending it.
  Anything that adds it later must re-list `node_modules`, or pytest starts walking
  apps/web's dependency tree.
- **mypy has the same duplicate-module hazard** as pytest's prepend mode. Today's test
  module names are unique so `mypy .` is green; if two same-named test modules ever
  land in directories without `__init__.py`, the fix is `explicit_package_bases` /
  `mypy_path`, not renaming the tests.

## Not in this phase

- Any model/AI call — deferred to Phase 1
- LiteLLM Proxy service in docker-compose — deferred to Phase 1
- LangGraph workflow — deferred to Phase 2
- Structured summaries — deferred to Phase 3
- Safety pipeline — deferred to Phase 4
- Observability, Phoenix + OTel services in docker-compose — deferred to Phase 5
