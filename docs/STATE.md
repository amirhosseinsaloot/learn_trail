# State

Current phase: **Phase 1 is COMPLETE. Phase 2 — LangGraph workflow is next**
(see [plans/phase-2.md](../plans/phase-2.md)); nothing in Phase 2 has been started.

`make status` reports **Phase 0 PASS, Phase 1 PASS**. Phases 2–12 are red, as
designed.

All six Phase 1 tasks: `chat`+`message` tables and the async session `421feb8`,
the LiteLLM gateway and its three aliases `e9a9118`, the chat endpoints
`41808f1`, the typed gateway client `773b4a8`, the SSE answer endpoint `f05f900`,
the chat page `2b6228c`, and the real phase test `1e092b1`.

The end-to-end chat works against a real provider: ask a question in the browser,
watch the answer stream in, stop and restart the backend, and continue the same
conversation. `tests/phases/test_phase_1.py` asserts that by actually restarting
the container — it makes **no model call**, because it runs on every
`make status`.

Next: Phase 2's four tasks. Its own task list frames it as a refactor —
"replace the Phase 1 direct call with a call into the graph from the chat
endpoint" — so the seam it replaces is `stream()` in
`apps/api/api/routers/chats.py`, and `_working_context` there is what becomes the
`build_context` node.

Phase 0 tasks, for reference: task 1 `1de4a59`, 2 `1a603eb`, 3 `0c56b7f`,
4 `2b0e933`, 5 `06b9736`, 6 `6132a66`, 7 `600d919`, 8 `e7bed57`, 9 `872bcb5`.
Phase 0's exit criterion was verified by running it, and still passes with four
services.

**Phase 2 was requested and is blocked on Phase 1.** Phase 2's own task list says
"replace the Phase 1 direct call with a call into the graph from the chat
endpoint", and SPEC §15 words it the same way — it is a refactor of Phase 1's
code. There is no chat endpoint to convert, nothing for `persist` to write
through, and nothing for the checkpointer to key on. Phase 1's four remaining
tasks are the prerequisite, not a detour.

Next task: the chat endpoints. `packages/ai_core` is still `.gitkeep`-only and is
**not** a uv workspace member — adding it to `[tool.uv.workspace] members` in the
root pyproject.toml is part of the task that first puts code there.

## In-flight / half-done

One open item, and one resolved note worth keeping:

- **RESOLVED — the gateway now reaches a real provider.** `.env` exists with a
  working `OPENAI_API_KEY`, and all three aliases were called live: `learning-fast`
  → `gpt-4o-mini-2024-07-18`, `learning-deep` → `gpt-4o-2024-08-06`,
  `safety-judge` → `gpt-4o-mini-2024-07-18`. The credential boundary was
  re-checked *after* the key landed, which is the moment it could have leaked:
  `printenv` in both the backend and frontend containers shows no provider key
  (CLAUDE.md invariant #3 holds). `.env` is gitignored; `.env.example` holds only
  placeholders.

  Note for anyone editing `.env` later: `env_file` is read when the container is
  *created*, so a changed `.env` needs
  `docker compose up -d --force-recreate litellm` — a plain `restart` keeps the
  old environment and the change looks like it did nothing.
- **gitleaks is still inert.** lefthook.yml skips it when the binary is missing,
  and the first credential path now exists, so this is overdue. Arming it means
  installing the binary first, then deleting the `if`/`else`/`fi` guard as
  lefthook.yml's own comment instructs. Arming it before installing would
  hard-fail every commit.

- **A frontend dependency change needs the anonymous volume renewed.**
  `apps/web/node_modules` is an anonymous volume seeded from the image, so
  `pnpm add` on the host never reaches the container. It needs
  `docker compose build frontend` **and**
  `docker compose up -d --force-recreate --renew-anon-volumes frontend`;
  without the renewal the container keeps its old dependency tree and fails with
  module-not-found. Same family of trap as the `env_file` note above.

Also worth knowing: the Docker **images are built and the stack may still be
running** on this machine (`make ps`). `make down` keeps the `postgres_data`
volume; `docker compose down -v` throws the data away. The database is migrated
to `head` — one revision, `chat` and `message` — and **has zero rows**: every
end-to-end verification cleaned up after itself, and the Phase 1 phase test
purges its own chat on each run.

## What exists right now

- `docs/SPEC.md` — the full product/architecture spec.
- `CLAUDE.md` — cross-phase invariants.
- `.claude/agents/` — six subagents for Phase 0–3 boundaries (`backend-api`,
  `frontend-web`, `ai-orchestration`, `infra-devops`, `prompt-librarian`,
  `architecture-reviewer`). The Phase 4+ agents named in the subagent design
  (`safety-engineer`, `observability-engineer`, `eval-engineer`, `red-team`,
  `retrieval-engineer`, `prompt-optimizer`) do not exist yet — add each when its phase
  starts.
- `tests/phases/test_phase_0.py` — **real**, and green; it now covers four
  services. `test_phase_1.py` … `test_phase_12.py` are still intentionally
  failing placeholders.
- `docs/ARCHITECTURE.md` — the one-page structural view (layers, request path,
  approval gate, data model, dependency direction), with the phase that
  introduces each component.
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
  `api.main:app` is a thin entrypoint that includes `api.routers.chats`; handlers
  live in `api/routers/`, wire schemas in `api/schemas.py`. Surface:
  `GET|POST /chats`, `GET|PATCH|DELETE /chats/{id}`, `POST /chats/{id}/restore`,
  `POST /chats/{id}/messages`. No auth, no CORS yet (CORS lands with the first
  browser fetch). Runtime deps: fastapi, pydantic, uvicorn, learntrail-database.
- `packages/database/` — `learntrail-database`, exposing top-level `database`.
  `Base` + a constraint naming convention, `database_url()` reading
  `DATABASE_URL`, an async engine and session factory in `database/session.py`,
  and `database/models/conversation.py` with `Chat` and `Message`. **One** Alembic
  revision (`6ab72a617d4e`, `chat` + `message`), verified to rebuild from an empty
  database with no drift. Driver: psycopg 3. Deps: alembic, psycopg[binary],
  sqlalchemy[asyncio].
- One root `pytest.ini` discovering `tests/`, `apps/` and `packages/` under
  `--import-mode=importlib`. `pytest` from the root: **12 failed, 10 passed** — the 12
  remaining phase placeholders are red on purpose; the 8 unit tests in
  `apps/api/tests/` and `packages/database/tests/` plus the 2 real Phase 0 phase tests
  pass. Which of the four test homes a new test belongs in is written down in
  [CLAUDE.md](../CLAUDE.md).
- A pnpm workspace at the root (`package.json`, `pnpm-workspace.yaml`, committed
  `pnpm-lock.yaml`, `biome.jsonc`) with one member, `apps/web`. Biome lives at the root;
  Next/React/TS/ESLint in `apps/web`.
- `apps/web/` — Next.js App Router + React + Tailwind. **The chat page**: ask a
  question, watch the answer stream in, list and resume conversations.
  `src/lib/api/client.ts` (openapi-fetch, typed from the generated
  `schema.gen.ts`) and `src/lib/api/stream.ts` (SSE via `fetch` +
  ReadableStream — `EventSource` cannot be used, it is GET-only). Biome
  (format + fast lint), typescript-eslint (type-aware rules only) +
  `@next/eslint-plugin-next`, `tsc --noEmit` with `strict`,
  `noUncheckedIndexedAccess` and `allowJs: false`. All green.
- Frontend commands: root `pnpm run lint:web` / `type:web`; in `apps/web`, `dev`,
  `build`, `lint`, `typecheck` (= `next typegen && tsc --noEmit` — the prefix is
  load-bearing, the tsconfig includes generated files).
- `lefthook.yml` + installed `.git/hooks`. pre-commit (~0.1s) autofixes and re-stages
  staged files; pre-push (~5s) runs `make lint-py type-py type-web lint-web test`.
  gitleaks is wired but inert until Phase 1. `make help` lists every target;
  `make fast` runs the whole Phase 0 check set.
- `docker-compose.yml` + `.dockerignore` + `infra/docker/{backend,frontend}.Dockerfile`
  — **four services**, each with a real healthcheck: `postgres` (18-alpine,
  5432 published, named `postgres_data` volume), `backend` (uvicorn `--reload` on
  bind-mounted source, venv at `/opt/venv` outside `/app`, 8000 published), `frontend`
  (`next dev`, anonymous volumes over `node_modules` and `.next`, 3000 published),
  and `litellm` (**no host port** — in-network only at `http://litellm:4000`).
  Both built images are development images running as uid 1000; production stages
  land when there is something to deploy. Driven by `make up` / `down` / `logs` / `ps`.
- `packages/ai_core/` — `learntrail-ai-core`, exposing top-level `ai_core`.
  `models/aliases.py` (the `ModelAlias` enum — invariant #2 as a type),
  `schemas/completion.py` (typed request/response — invariant #4), and
  `models/gateway.py`, **the only module in the repo permitted to import a
  provider SDK** (docs/CODE_QUALITY.md's Semgrep rule excludes exactly that
  path). `graphs/`, `agents/`, `safety/`, `telemetry/`, `retrieval/` are still
  empty and each arrives with its phase. Deps: openai (as an HTTP client for the
  OpenAI-*compatible* proxy), pydantic.
- `infra/litellm/config.yaml` — the three aliases (`learning-fast` and
  `safety-judge` → `openai/gpt-4o-mini`, `learning-deep` → `openai/gpt-4o`), each
  reading `OPENAI_API_KEY` from the environment. **The only place a provider is
  named.** Verified live: `/v1/model/info` shows the mapping, and the backend
  holds no provider credential (checked with `printenv` inside the container,
  not assumed).
- **No CI.** Hooks and `make fast` are the only enforcement, and both are bypassable
  with `--no-verify`. The FAST CI lane moved to Phase 1.

---

Written by a model. Verify with `make status` before acting on anything above — this
file is a claim, not a fact.
