# Phase 1 — Basic AI chat

Status: Not started

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> You can stop the application, restart it and continue a previous conversation.

## Phase test

`tests/phases/test_phase_1.py`

## Tasks

- [ ] Create-chat, send-message, resume-conversation, rename-chat, soft-delete-chat endpoints (owner: `backend-api`) — commit: `____`
- [ ] chat and message tables + Alembic migration (no user_id column) (owner: `backend-api`) — commit: `____`
      - Phase 0 set a constraint naming convention on the empty `Base`, and its
        `ck` template interpolates `%(constraint_name)s`: every `CheckConstraint`
        must be given an explicit `name=`, or DDL compilation raises a confusing
        `InvalidRequestError`.
      - Switch `packages/database` to `sqlalchemy[asyncio]` when the async
        request-path session lands — `create_async_engine` needs greenlet, which
        today arrives only via SQLAlchemy's platform markers.
- [ ] Add the LiteLLM Proxy service to docker-compose.yml (it joins in this phase, not Phase 0 — a service enters compose in the phase that introduces its concept) and configure it with one cloud model alias (learning-fast or equivalent) (owner: `infra-devops`) — commit: `____`
      - **This task must also widen `PHASE_0_SERVICES` in
        `tests/phases/test_phase_0.py`, in the same commit.** That test asserts the
        compose service list by set *equality* (deliberately — it is how invariant #6
        is enforced mechanically), so adding a fourth service flips Phase 0 to FAIL
        until the constant names it. Give LiteLLM a healthcheck at the same time:
        the same test requires every service to declare one.
      - Phase 0's compose has **no `.env` and no secret** — the Postgres password is
        the throwaway literal `learntrail`, inline. LiteLLM is the first service
        needing a real provider credential (invariant #3: server-side only, never
        reaching the frontend), so this is where `.env` + `env_file:` arrive, and
        where gitleaks stops being inert. `.dockerignore` already excludes `.env`
        and `.env.*` so an image cannot absorb one.
      - The backend gets `depends_on: litellm` only if it calls the proxy at
        startup; a request-path-only dependency does not need it.
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
