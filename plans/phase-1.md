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
- [ ] Direct LiteLLM call wrapped in Pydantic request/response models (pre-LangGraph) (owner: `ai-orchestration`) — commit: `____`
- [ ] SSE streaming endpoint for answers (owner: `backend-api`) — commit: `____`
- [ ] Chat page: send question, render streamed answer, list/resume chats (owner: `frontend-web`) — commit: `____`

## Not in this phase

- LangGraph workflow (direct model call only, no graph) — deferred to Phase 2
- Structured summary generation — deferred to Phase 3
- Safety pipeline — deferred to Phase 4
- Observability — deferred to Phase 5
