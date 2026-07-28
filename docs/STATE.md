# State

Current phase: **Phase 4 is COMPLETE. Phase 5 — Observability is next**
(see [plans/phase-5.md](../plans/phase-5.md)); nothing in Phase 5 has been
started.

`make status` reports **Phase 0, 1, 2, 3 and 4 PASS**. Phases 5–12 are red, as
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

Phase 2 replaced the direct model call with a LangGraph workflow (`29c8be0`).
A chat request now walks five nodes —
`validate_input -> build_context -> choose_model -> generate_answer -> persist` —
and the Postgres checkpointer records each one, so a request can be replayed out
of storage afterwards. That replay is what `tests/phases/test_phase_2.py`
asserts.

Phase 3 added the approval gate. A conversation can be summarised into a
`summary_draft` by a second graph
(`load_chat -> prepare_context -> generate_summary -> validate_summary ->
store_draft -> await_approval -> apply_decision`), reviewed and edited in the UI,
and promoted to a `learning` **only** by an explicit approval that resumes the
graph's interrupt. Every Learning carries a revision history distinguishing text
that came from a model draft (`model`) from text the user wrote (`human`).

Phase 4 added the safety pipeline (`bf0fbdf`, `076497f`, and the UI/phase-test
commit). A chat request now walks seven nodes —
`validate_input -> input_safety_check -> build_context -> choose_model ->
generate_answer -> output_safety_check -> persist` — with the graph's **first two
conditional edges**, both routing a refusal to END. `test_chat_graph.py`'s
no-branches assertion was replaced, deliberately, by a narrower one: only the two
safety checks branch, and a third branch anywhere has to argue for itself.

Every decision is written to `safety_event`, allow included — "checked and fine"
has to be distinguishable from "never checked", which is what the criterion means
by *explicit*. Verified live: a prompt injection is blocked at the input stage
with zero tokens generated and no message row; a benign question streams and
persists; an API key plus an email warns at both stages and is answered anyway.

Three limits are real and carried forward, all documented in
[plans/phase-4.md](../plans/phase-4.md): the output check runs *after* tokens have
streamed (never persisted, client told to discard); PII detection is regex, so it
finds structured identifiers and not names; and the rails **fail open** — a judge
model that is down allows the message with a warning recorded rather than taking
the product down with it.

Next: Phase 5, observability. Note it will want `model_run`, which the chat
graph's `persist` node is already the natural home for, and Phoenix/OTel wiring
in `infra/`.

Phase 0 tasks, for reference: task 1 `1de4a59`, 2 `1a603eb`, 3 `0c56b7f`,
4 `2b0e933`, 5 `06b9736`, 6 `6132a66`, 7 `600d919`, 8 `e7bed57`, 9 `872bcb5`.
Phase 0's exit criterion was verified by running it, and still passes with four
services.

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
- **The plan's `safety-engineer` agent was never created.** Phase 4's rails and
  validators were built by `ai-orchestration`, which already owns
  `packages/ai_core`, rather than inventing an agent mid-phase. Worth deciding
  before Phase 7 (red teaming), which is the next phase that would want a
  dedicated safety owner.

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
- `tests/phases/test_phase_0.py` … `test_phase_3.py` — **real**, and green.
  `test_phase_4.py` … `test_phase_12.py` are still intentionally failing
  placeholders. Only the Phase 2 test calls a model; the others deliberately do
  not, since `make status` runs them all.
- `docs/ARCHITECTURE.md` — the one-page structural view (layers, request path,
  approval gate, data model, dependency direction), with the phase that
  introduces each component.
- `plans/phase-0.md` … `phase-12.md` — task breakdown per phase.
- `docs/decisions/` — ADR template + 0001 (why exit criteria are executable).
- The SPEC §16 directory tree (`apps/`, `packages/`, `tests/`, `prompts/`, `infra/`).
  `packages/ai_core/prompts/` is deliberately absent — top-level `prompts/` is
  canonical. `packages/evals/` is still `.gitkeep`-only and not a uv workspace
  member; it joins in Phase 6.
- Root `pyproject.toml` + committed `uv.lock` + `.python-version` (3.12) + `README.md`.
  `uv sync --all-groups` builds `.venv/` with pytest 9.1.1, ruff 0.16.0, mypy 2.3.0.
  The root is a uv workspace aggregator (`package = false`) with three members:
  `apps/api`, `packages/ai_core` and `packages/database`.
- Ruff (Tier 1 rule sets, 100 cols) and mypy (strict + Pydantic plugin) are configured
  in the root `pyproject.toml` and **green across the repo**.
- `apps/api/` — `learntrail-api`, a hatchling distribution exposing top-level `api`.
  `api.main:app` is a thin entrypoint that includes `api.routers.chats`; handlers
  live in `api/routers/`, wire schemas in `api/schemas.py`, SSE framing in
  `api/sse.py`, and the compiled graph's lifetime in `api/graph.py`. Surface:
  `GET|POST /chats`, `GET|PATCH|DELETE /chats/{id}`, `POST /chats/{id}/restore`,
  `POST /chats/{id}/messages`, `POST /chats/{id}/answer`. No auth; CORS allows one
  origin from `WEB_ORIGIN`. Runtime deps: fastapi, pydantic, uvicorn,
  learntrail-ai-core, learntrail-database.
- `packages/database/` — `learntrail-database`, exposing top-level `database`.
  `Base` + a constraint naming convention, `database_url()` reading
  `DATABASE_URL`, an async engine and session factory in `database/session.py`,
  and `database/models/conversation.py` with `Chat` and `Message`. **One** Alembic
  revision (`6ab72a617d4e`, `chat` + `message`), verified to rebuild from an empty
  database with no drift. Driver: psycopg 3. Deps: alembic, psycopg[binary],
  sqlalchemy[asyncio].
- One root `pytest.ini` discovering `tests/`, `apps/` and `packages/` under
  `--import-mode=importlib`. `pytest` from the root: **10 failed, 102 passed,
  1 skipped** — the 10 remaining phase placeholders are red on purpose, the skip
  is the paid live-gateway test (`-m slow`), and the rest are the unit tests in
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
  path). `graphs/` holds the Phase 2 chat workflow: `chat.py` (five nodes,
  no `database` import — persistence is injected), `messages.py` (LangChain
  message adapters) and `checkpointer.py` (Postgres, one thread per request).
  `agents/`, `safety/`, `telemetry/`, `retrieval/` are still empty and each
  arrives with its phase. Deps: openai (as an HTTP client for the
  OpenAI-*compatible* proxy), langgraph, langchain-core,
  langgraph-checkpoint-postgres, pydantic.
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
