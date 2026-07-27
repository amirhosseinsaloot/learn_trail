# Phase 3 — Structured summary generation

Status: COMPLETE — all 5 tasks landed; `make status` reports Phase 3 PASS.

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> Malformed or incomplete summaries are rejected before persistence.

## Phase test

`tests/phases/test_phase_3.py`

## Tasks

- [x] Author and version the learning_summary prompt (owner: `prompt-librarian`) — commit: `df381ea`
      - TOML parsed with stdlib `tomllib` — no YAML dependency, and no block-scalar
        indentation traps. One file per version, never edited in place.
      - Only an `active` version loads, and two active versions is an error: a
        recorded `prompt_version` must identify exactly one text.
      - **`.dockerignore` excluded `prompts/`**, correct when it held a .gitkeep
        and wrong once it held runtime content. The image booted fine and would
        have failed on the first summary a user asked for.
- [x] Pydantic AI summary-generation task with the LearningSummary schema (docs/SPEC.md §7) (owner: `ai-orchestration`) — commit: `df381ea`
      - The Pydantic AI model is built inside `gateway.py`, the one module allowed
        to import a provider SDK, so `ai_core.agents` needs no Semgrep exception.
      - **An alias must not carry `max_tokens`.** LiteLLM translates a caller's
        `max_tokens` to `max_completion_tokens`, so an alias-level one makes the
        provider receive both spellings and reject the request. Ceilings belong to
        callers.
- [x] Add Guardrails AI schema validators + LangGraph approval interrupt to the summary graph (owner: `ai-orchestration`) — commit: `8e9abaa`
      - Custom validators, **not Guardrails Hub**: Hub validators download at
        runtime and need an account, making a summary depend on a third party.
      - **A vocabulary-overlap check false-positives on short transcripts.** The
        first version rejected a correct summary of a two-turn exchange. It now
        needs a substantial source before firing, and says in its docstring that
        string matching is a weak proxy — the real check is a judge model in
        Phase 6.
      - `await_approval` is invariant #5 made structural: the graph stops and only
        a human-supplied resume value reaches `apply_decision`.
- [x] summary_draft, learning, learning_revision tables + endpoints (edit/regenerate/approve) (owner: `backend-api`) — commit: `8e9abaa`, `7138ee0`
      - Separate tables, not an `approved` flag, so a query that forgets to filter
        returns nothing rather than promoting model output.
      - `learning.source_chat_id` is **SET NULL**, not CASCADE: deleting a
        conversation must not delete the knowledge derived from it.
      - Approval **resumes the interrupted graph**; the draft id is generated in
        the handler before the run so the interrupt's thread is knowable.
      - **`alembic check` began demanding removal of LangGraph's checkpoint
        tables.** Generating that migration would drop every recorded graph
        execution, including interrupted approvals. `env.py` now filters
        autogenerate to tables in our own metadata.
      - Editing a Learning returned a *stale* revision list: the identity map
        holds the collection loaded before the insert, and
        `expire_on_commit=False` means commit does not invalidate it.
- [x] Summary review UI: edit, regenerate, approve; My Learnings + revision history views (owner: `frontend-web`) — commit: `see below`
      - The review panel saves pending edits *before* approving: approval
        promotes what the server holds, so approving unsaved edits would quietly
        promote the pre-edit text.
      - A pending draft is re-fetched when a chat is opened — it lives in the
        database, not in component state.
      - `listField()` narrows the generated optional list types once, rather than
        `?? []` at every read where one omission is a render crash.

## Not in this phase

- NeMo Guardrails / provider moderation / PII rails — deferred to Phase 4
- Observability instrumentation — deferred to Phase 5
- Evaluation suite — deferred to Phase 6
- Retrieval over approved learnings — deferred to Phase 8
