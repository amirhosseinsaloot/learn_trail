# State

Current phase: **Phase 1 — Basic AI chat, IN PROGRESS.** Phase 0 is complete.
See [plans/phase-1.md](../plans/phase-1.md).

`make status` reports **Phase 0 PASS**, phases 1–12 FAIL. Phase 1's red is
correct: its exit criterion (stop the app, restart, continue a conversation) is
not met, because there is no chat endpoint yet.

Phase 1 progress — **3 of 6 tasks landed**:

- [x] `chat` + `message` tables + first Alembic revision + async session — `421feb8`
- [x] LiteLLM gateway service + the three aliases — `e9a9118`
- [x] Chat endpoints: create / list / resume / rename / soft-delete / restore /
      append a user turn — `41808f1`
- [ ] LiteLLM call wrapped in Pydantic models (`packages/ai_core`, not yet a member)
- [ ] SSE streaming endpoint (the answer half of "send a message")
- [ ] Chat page in `apps/web`
- [ ] Replace the `tests/phases/test_phase_1.py` placeholder

**The persistence half of the Phase 1 exit criterion is already demonstrated**,
against the running stack rather than a test client: create a chat, append two
messages, `docker compose stop backend && start backend`, GET the chat — the
transcript comes back intact. What is missing for the criterion proper is an
answer to resume *to*, i.e. the model call and the SSE endpoint.

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

Two things `git log` cannot show, both still open:

- **No `.env`, and `.env.example` still names the wrong variable.** The provider
  moved to OpenAI, so the gateway reads `OPENAI_API_KEY` — but `.env.example`
  (committed at `e6616d6`, before the switch) still says `ANTHROPIC_API_KEY`.
  The agent cannot fix it: its permission settings deny both reads and writes
  under `.env*`. Do this by hand:

  ```
  printf 'OPENAI_API_KEY=\nLITELLM_MASTER_KEY=sk-local-dev-change-me\n' > .env.example
  cp .env.example .env    # then paste the real key into .env
  ```

  Until then **no model call can succeed**. The stack stays healthy regardless —
  `env_file` uses `required: false` and the healthcheck probes liveliness, not
  providers — so this surfaces only on the first real call, as a clear
  `AuthenticationError` naming `OPENAI_API_KEY` (verified).
- **gitleaks is still inert.** lefthook.yml skips it when the binary is missing,
  and the first credential path now exists, so this is overdue. Arming it means
  installing the binary first, then deleting the `if`/`else`/`fi` guard as
  lefthook.yml's own comment instructs. Arming it before installing would
  hard-fail every commit.

Also worth knowing: the Docker **images are built and the stack may still be
running** on this machine (`make ps`). `make down` keeps the `postgres_data`
volume; `docker compose down -v` throws the data away. The database is migrated
to `head` — one revision, `chat` and `message` — and **has zero rows**: the
end-to-end verification above wrote a chat and two messages, then hard-deleted
them (which also exercised `ON DELETE CASCADE` against real data).

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
  — **four services**, each with a real healthcheck: `postgres` (18-alpine,
  5432 published, named `postgres_data` volume), `backend` (uvicorn `--reload` on
  bind-mounted source, venv at `/opt/venv` outside `/app`, 8000 published), `frontend`
  (`next dev`, anonymous volumes over `node_modules` and `.next`, 3000 published),
  and `litellm` (**no host port** — in-network only at `http://litellm:4000`).
  Both built images are development images running as uid 1000; production stages
  land when there is something to deploy. Driven by `make up` / `down` / `logs` / `ps`.
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
