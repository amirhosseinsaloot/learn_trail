# LearnTrail

Single-user AI learning workspace and AI-engineering laboratory. Full product and architecture spec: [overview.md](overview.md). Read it before making structural decisions — this file only holds the invariants that every subagent must respect.

## Non-negotiable invariants

These apply across `apps/`, `packages/`, `prompts/`, and `infra/` regardless of which subagent is doing the work. Do not restate or fork these per-agent — if an agent prompt disagrees with this file, this file wins.

1. **No auth, no users.** No `user` table, no `user_id` column, no login, no roles, no organizations. This is a single-person private workspace. See overview.md §1, §18.
2. **No direct provider calls.** Every model call goes through LiteLLM using a model alias (`learning-fast`, `learning-deep`, `safety-judge`) — never a hard-coded provider/model string in application code. See overview.md §7, §13.
3. **Model credentials never reach the browser.** Provider API keys and LiteLLM proxy credentials stay server-side. The frontend never sees them and never calls a model API directly.
4. **LangGraph owns orchestration; Pydantic AI implements typed tasks inside graph nodes.** Don't let the two compete for control of the workflow. Don't reach for a prebuilt high-level agent when a deterministic LangGraph workflow is clearer.
5. **Every structured model output is parsed into a Pydantic schema** before it touches persistence or the response. Malformed or incomplete output is rejected or retried, never passed through.
6. **Human approval is a hard checkpoint.** The model may draft a summary; it can never promote a draft into an approved learning, edit an approved learning, delete one, or merge two, without an explicit user action. See overview.md §4, §8 (Layer 6).
7. **Safety is a pipeline, not a single call.** Input validation → provider moderation → NeMo Guardrails → Guardrails AI → Pydantic validation → human approval. Don't collapse these layers or treat one as a substitute for another. See overview.md §8.
8. **Standard app security still applies.** Parameterized queries, sanitized Markdown/HTML rendering, request timeouts, model-call budgets, no direct execution of generated code. AI safety frameworks do not replace this.
9. **Prompts are versioned, not inline.** Prompt definitions live under `prompts/` with `name`, `version`, `status` (`draft` → `candidate` → `active` → `retired`). Every trace and evaluation result records the `prompt_version` used. A candidate is promoted only after passing the evaluation suite — never on a few good-looking examples.
10. **One new AI concept per phase.** Don't introduce a framework, safety layer, or evaluation tool ahead of the roadmap phase that calls for it (overview.md §15). Don't run two overlapping frameworks for the same job (e.g. two observability backends) outside of an explicit comparison exercise.

## Repository ownership

See overview.md §16 for the full layout. Rough ownership by subagent:

- `apps/api/`, `packages/database/` — `backend-api`
- `apps/web/` — `frontend-web`
- `packages/ai_core/{graphs,agents,models,schemas,safety,retrieval,telemetry}` — `ai-orchestration` (and later `safety-engineer`, `observability-engineer`, `retrieval-engineer`)
- `prompts/` — `prompt-librarian`
- `infra/`, `docker-compose.yml` — `infra-devops`
- Everything, read-only — `architecture-reviewer`

## Current phase

The repo is at Phase 0 (overview.md §15): nothing is built yet beyond this spec. Don't jump ahead to safety frameworks, evaluation suites, or retrieval — those subagents and their code don't exist until the roadmap reaches them.
