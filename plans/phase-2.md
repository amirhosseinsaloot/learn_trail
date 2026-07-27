# Phase 2 — LangGraph workflow

Status: COMPLETE — all 4 tasks landed; `make status` reports Phase 2 PASS.

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> Each chat request is visible as a deterministic graph execution.

## Phase test

`tests/phases/test_phase_2.py`

## Tasks

- [x] Build the validate_input -> build_context -> choose_model -> generate_answer -> persist graph (owner: `ai-orchestration`) — commit: `29c8be0`
      - The graph does **not** import `database`: persistence is an injected
        callable on the run config, so the workflow runs with no Postgres and no
        session. ARCHITECTURE §7 would allow the import; not needing it is what
        makes every node a function of its inputs.
      - Determinism is asserted structurally (no node has more than one outgoing
        edge), so Phase 4's branch must be a deliberate change to that test.
- [x] Wire LangChain model/message adapters into the graph nodes (owner: `ai-orchestration`) — commit: `29c8be0`
      - LangChain supplies the message *vocabulary* (`BaseMessage`, needed by
        `add_messages` and the checkpointer's serialization); the model call still
        goes through the gateway alias. **No `ChatOpenAI`** — that would be a
        second place a provider is named, which invariant #2 exists to prevent.
- [x] Add a Postgres checkpointer for graph state (owner: `ai-orchestration`) — commit: `29c8be0`
      - **Thread id is `{chat_id}:{sequence_number}`, one per request.** Threading
        by chat id alone re-feeds prior turns into `add_messages` and doubles the
        working context every turn — measured [1, 5, 11] over three turns against
        an expected [1, 3, 5]. It does not error; it just costs money.
      - LangGraph's checkpoint tables are created by `setup()` in the app
        lifespan and are **outside Alembic** — the library owns their schema.
      - Register any type that reaches graph state in the checkpointer's serde
        (`ALLOWED_CHECKPOINT_TYPES`). Unregistered types warn now and will be
        blocked in a future version, which would make existing checkpoints
        unreadable on a dependency bump.
- [x] Replace the Phase 1 direct call with a call into the graph from the chat endpoint (owner: `backend-api`) — commit: `29c8be0`
      - The endpoint's HTTP-level checks survive the move and are **not**
        duplicates of `validate_input`: they exist to produce status codes, and a
        status code can only be sent before the stream opens.
      - `stream_mode=["custom"]` is what carries tokens — node updates only
        arrive after a node returns, so without it a streamed answer would land
        as one lump.
      - The refactor silently dropped Phase 1's empty-answer guard; the endpoint
        tests caught it. It now lives in `generate_answer`.

## Not in this phase

- Structured summary generation — deferred to Phase 3
- Safety pipeline — deferred to Phase 4
- Observability — deferred to Phase 5
