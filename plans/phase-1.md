# Phase 1 — Basic AI chat

Status: IN PROGRESS — 3 of 6 tasks landed (tables, gateway, endpoints). Phase test
is still a placeholder, so `make status` reports Phase 1 FAIL, correctly.

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> You can stop the application, restart it and continue a previous conversation.

## Phase test

`tests/phases/test_phase_1.py`

## Tasks

- [x] Create-chat, send-message, resume-conversation, rename-chat, soft-delete-chat endpoints (owner: `backend-api`) — commit: `41808f1`
      - Answer generation is **not** in this task: docs/SPEC.md §6 lists "sending
        messages" and "streaming answers" separately, so `POST
        /chats/{id}/messages` persists the user turn and the SSE task adds the
        answer endpoint. That split is what makes these endpoints testable with
        no model and no key.
      - **Two async-SQLAlchemy traps, both of which produce a 500 on the happy
        path and neither of which a sync session would show:**
        (1) serializing a model with an unloaded relationship is lazy IO from
        Pydantic's synchronous attribute access → `MissingGreenlet`; pass
        `messages=[]` on a newly-constructed `Chat` to mark the collection
        loaded. (2) `onupdate` is evaluated by the *database*, so after any
        UPDATE the ORM marks `updated_at` stale and reading it back blows up —
        every mutate-then-return handler needs
        `await db.refresh(chat, attribute_names=["updated_at"])`.
        `expire_on_commit=False` does **not** cover this; the staleness comes
        from the server-side default, not the commit.
      - **`now()` is `transaction_timestamp()` in Postgres and is frozen for the
        whole transaction.** Anything ordered by a `now()`-maintained column
        silently fails to reorder when two writes share a transaction. Both the
        column's `onupdate` and the explicit touch use `clock_timestamp()`.
        `onupdate` is ORM-side, not DDL, so no migration was needed —
        `alembic check` confirms.
      - `lazy="selectin"` means a list query fetches every message of every
        listed chat. The list endpoint uses `noload`.
      - **As of FastAPI 0.140 `include_router` does not flatten routes into
        `app.routes`** — it inserts a private `_IncludedRouter`. A test that
        enumerates `app.routes` finds only the four built-in doc routes and
        passes while asserting nothing. Assert the surface through
        `app.openapi()["paths"]`, which is also the real contract (the frontend's
        types are generated from it).
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
