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
- [ ] Add Alembic under packages/database/ and wire it to the Postgres service.
      No models/tables yet — Phase 1 adds `chat`/`message`; this task ends at an
      empty, runnable migration env (owner: `backend-api`) — commit: `____`
- [ ] Extend the root pytest.ini so apps/api/ and packages/database/ tests are
      discovered — single root config, no per-package pytest configs
      (owner: `backend-api`) — commit: `____`
- [ ] Scaffold apps/web/ Next.js + TypeScript + Tailwind skeleton with Biome
      (format + fast lint), typescript-eslint (type-aware rules only), and
      `tsc --noEmit` with `strict` + `noUncheckedIndexedAccess`
      (owner: `frontend-web`) — commit: `____`
- [ ] lefthook root config: pre-commit (ruff, biome, gitleaks-ready), pre-push
      (mypy, tsc, unit tests); plus `make` targets so every check runs locally
      with one command (owner: `infra-devops`) — commit: `____`
- [ ] Write docker-compose.yml: Postgres, backend, frontend — each with a healthcheck
      (owner: `infra-devops`) — commit: `____`
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
- **pytest 9 import mode.** When pytest discovery is extended to `apps/api/` and
  `packages/database/`, same-named test modules in directories without `__init__.py`
  collide under the default import mode. Resolve in the single root config.

## Not in this phase

- Any model/AI call — deferred to Phase 1
- LiteLLM Proxy service in docker-compose — deferred to Phase 1
- LangGraph workflow — deferred to Phase 2
- Structured summaries — deferred to Phase 3
- Safety pipeline — deferred to Phase 4
- Observability, Phoenix + OTel services in docker-compose — deferred to Phase 5
