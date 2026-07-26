# Phase 1 — Basic AI chat

Status: COMPLETE — all 6 tasks landed; `make status` reports Phase 1 PASS.

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
      - **Provider switched from Anthropic to OpenAI after this task landed, at
        the user's request** — and the switch was one file. `infra/litellm/config.yaml`
        plus two prose lines in docs/STATE.md; no application code, no schema, no
        test, and the three alias names never changed. That is invariant #2
        paying for itself, and it is the answer to "why not just call the SDK".
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
- [x] Direct LiteLLM call wrapped in Pydantic request/response models (pre-LangGraph) (owner: `ai-orchestration`) — commit: `773b4a8`
      - `ModelAlias` is an enum, not a `str`: invariant #2 becomes a type error
        rather than a convention. `CompletionResponse.from_provider` is the only
        route from provider payload to usable object (invariant #4), and it
        raises on a missing usage block instead of defaulting to zeros — Phase 5
        bills on those numbers and Phase 6 evaluates on them.
      - **The OpenAI SDK's message roles are separate TypedDicts**, so
        `{"role": turn.role, "content": ...}` in a comprehension is
        `dict[str, str]` and matches none of them. Needs a per-role `match`
        so mypy can narrow. Expect this again in Phase 2 when LangChain message
        types enter.
      - A new workspace member must also be added to Ruff's
        `known-first-party`, or its imports sort as third-party.
      - `litellm` now publishes **127.0.0.1:4000** (loopback only) so the live
        gateway test can run at all — the image has no pytest and the gateway
        was previously in-network only. The live test is marked `slow`, so
        `make test` skips it; run it with `pytest -m slow`.
      - No `temperature` and no client-side retries, both deliberate and argued
        in the code: reasoning-tier models reject sampling params under
        `drop_params: false`, and retry/fallback is the gateway's job.
- [x] SSE streaming endpoint for answers (owner: `backend-api`) — commit: `f05f900`
      - **Validate before the response begins.** Once a stream is open the status
        line is sent, so 404/409 is no longer expressible — the error would have
        to be an SSE `error` event a client may ignore.
      - **Persistence hangs off the final chunk only.** A stream that dies
        partway leaves the chat untouched; a half-answer recorded as complete is
        not recoverable, and from Phase 3 these become Learnings.
      - `stream_options={"include_usage": True}` is mandatory — without it a
        streamed call returns no usage block at all.
      - The request-scoped `Depends(session)` **does** survive into a
        `StreamingResponse` generator on FastAPI 0.140 (verified end to end: the
        commit inside the generator worked). Do not assume this silently; if it
        ever changes, the fix is a dedicated session inside the generator.
      - Consume with `fetch` + ReadableStream, not `EventSource` — EventSource is
        GET-only and this is a POST because it creates a message.
      - Answering a chat whose last turn is an assistant message is a 409, or
        the model replies to itself.
- [x] Chat page: send question, render streamed answer, list/resume chats (owner: `frontend-web`) — commit: `2b6228c`
      - The base URL is resolved by the **browser**, which is outside the compose
        network, so `http://localhost:8000` is correct and `http://backend:8000`
        would not resolve. No `depends_on: backend` was added: the page renders
        and reports "is the backend running?" when the API is down, which is
        better than being un-startable.
      - **CORS lands here**, allowing one origin from the environment rather than
        `*`. There are no credentials to protect (invariant #1) — the exposure is
        who can make the app *act*, and acting spends money.
      - Types are generated by `openapi-typescript` from the live
        `/openapi.json` into `src/lib/api/schema.gen.ts`
        (`pnpm --filter web openapi:gen`). Hand-written Zod for API shapes stays
        forbidden — it would be a second source of truth that drifts.
      - **The frontend's `node_modules` is an anonymous volume seeded from the
        image.** A new dependency needs `docker compose build frontend` *and*
        `up --force-recreate --renew-anon-volumes`; without the volume renewal
        the container keeps its old tree and fails module-not-found.
      - Do not name a React prop `role` — it collides with the ARIA attribute and
        Biome rejects it. Use a domain word (`speaker`).
      - Type-aware ESLint rejects stashing an async callback's result in a
        mutable variable (it cannot narrow afterwards, so the value needs a cast
        that survives it being null). Return the value instead.
- [x] Replace the placeholder tests/phases/test_phase_1.py (owner: `backend-api`) — commit: `1e092b1`
      - Restarts the backend container for real, because "stop the application
        and restart it" cannot be asserted in-process.
      - **Deliberately makes no model call**: it runs on every `make status`, and
        billing the user to check project status is a bad trade. It also purges
        its own chat via the database (the API only soft-deletes).

## Not in this phase

- LangGraph workflow (direct model call only, no graph) — deferred to Phase 2
- Structured summary generation — deferred to Phase 3
- Safety pipeline — deferred to Phase 4
- Observability — deferred to Phase 5
