# Phase 1 — Basic AI chat

Status: IN PROGRESS — 2 of 6 tasks landed (tables + gateway). Phase test is still
a placeholder, so `make status` reports Phase 1 FAIL, correctly.

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> You can stop the application, restart it and continue a previous conversation.

## Phase test

`tests/phases/test_phase_1.py`

## Tasks

- [ ] Create-chat, send-message, resume-conversation, rename-chat, soft-delete-chat endpoints (owner: `backend-api`) — commit: `____`
- [x] chat and message tables + Alembic migration (no user_id column) (owner: `backend-api`) — commit: `421feb8`
      - Both forward-carried notes were hit and handled: `CheckConstraint`s all
        carry an explicit `name=`, and `packages/database` now depends on
        `sqlalchemy[asyncio]` with the async engine in `database/session.py`.
      - **Enum columns must use `Enum(native_enum=False, create_constraint=True,
        values_callable=...)`, not `String`.** With a plain `String` a fresh DB
        load returns `str`, not the enum — equality still works because StrEnum
        compares equal to `str`, so it passes every obvious test while mypy
        allows enum-only access that crashes at runtime. Each of those three
        arguments is non-default and load-bearing; without `values_callable` the
        database stores `'USER'` while every literal in the codebase says
        `'user'`, and without `create_constraint` SQLAlchemy 2.0 emits no CHECK.
      - `expire_on_commit=False` on the session factory is not style: the default
        refreshes on attribute access after commit, which on an async session
        raises `MissingGreenlet` mid-response.
      - `message.model_run_id` (docs/SPEC.md §17) is deliberately absent — it
        joins in the same migration that creates `model_run` (Phase 5).
- [x] Add the LiteLLM Proxy service to docker-compose.yml (it joins in this phase, not Phase 0 — a service enters compose in the phase that introduces its concept) and configure it with one cloud model alias (learning-fast or equivalent) (owner: `infra-devops`) — commit: `e9a9118`
      - All three aliases are declared (`learning-fast`, `learning-deep`,
        `safety-judge`), verified live via the gateway's `/v1/models`.
        `safety-judge` has no caller until Phase 4 — the alias *contract* is what
        invariant #2 is about, not the caller.
      - `PHASE_0_SERVICES` widened to four in the same commit, as this bullet
        required. Phase 0 still reports PASS.
      - **Healthcheck must be `/health/liveliness`, not `/health`.** `/health`
        actively pings every configured provider, so it fails without a real key
        — making the whole stack un-startable until a credential exists — and
        spends money on every probe.
      - **`env_file` must use `- path: .env` + `required: false`.** Without it
        compose refuses to start *any* service when `.env` is absent, so a clean
        clone could not run even the Phase 0 stack.
      - No host port published for `litellm`: the backend is the only intended
        caller, and an endpoint that spends money does not belong on the host
        network. The backend reaches it at `http://litellm:4000` via
        `LITELLM_BASE_URL`, and holds **no** provider credential (verified with
        `printenv` inside the container).
      - **STILL OPEN — `.env.example` is not committed.** The agent's own
        permission settings deny writes to `.env*`, so it could not be created.
        Its intended contents are recorded in docs/STATE.md; `.gitignore`
        already has the `!.env.example` negation waiting for it.
      - **STILL OPEN — gitleaks is not armed.** lefthook.yml's guard still skips
        when the binary is missing, and installing a Go binary is an environment
        step, not a repo change. Arming it (deleting the `if`/`else`/`fi` per
        lefthook.yml's own instructions) requires installing gitleaks first;
        doing it before that would hard-fail every commit.
- [ ] Direct LiteLLM call wrapped in Pydantic request/response models (pre-LangGraph) (owner: `ai-orchestration`) — commit: `____`
- [ ] SSE streaming endpoint for answers (owner: `backend-api`) — commit: `____`
- [ ] Chat page: send question, render streamed answer, list/resume chats (owner: `frontend-web`) — commit: `____`
      - Phase 0 deliberately gave `frontend` **no `depends_on: backend`** — the page
        was static, so coupling them would only have made the frontend un-startable
        whenever the API was down. This task adds the first fetch, so it is where
        that dependency belongs.
      - The frontend container reaches the API at `http://backend:8000` from inside
        the compose network, but browser-side code resolves from the host, where it
        is `http://localhost:8000`. A single `NEXT_PUBLIC_*` base URL cannot serve
        both; decide per call site which one runs where.

## Not in this phase

- LangGraph workflow (direct model call only, no graph) — deferred to Phase 2
- Structured summary generation — deferred to Phase 3
- Safety pipeline — deferred to Phase 4
- Observability — deferred to Phase 5
