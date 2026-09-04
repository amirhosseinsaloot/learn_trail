# State

Current phase: **The roadmap is COMPLETE. All 13 phases (0-12) PASS.**

`make status` reports every phase green. Both merge gates are satisfied: the
evaluation manifest and the red-team baseline each describe the current
configuration. There is no "next phase" — docs/SPEC.md defines phases 0 through
12 and every one is built, tested by its own executable exit criterion, and
mutation-checked.

## Phases 10-12, in brief

**Phase 10 — model routing.** `choose_model` (a one-line rule since Phase 2) now
classifies each question and routes simple ones to `learning-fast`, hard ones to
`learning-deep`. `generate_answer` tries the routed alias under a timeout and
falls back (`learning-deep -> learning-fast`) once if it hangs before streaming;
a failure after tokens have shown surfaces as an error rather than a second
model's answer overwriting the first. Cost-aware: a chat past its 24h ceiling
drops to the cheap path. Verified live — the strong model cost 13x the cheap one
at 2x the latency, shown on the `/models` dashboard.

**Phase 11 — local models.** `learning-local` is a gateway alias pointing at
Ollama, carrying no cloud credential; the `ollama` compose service ships
profile-gated (the optional runtime, not one of the mandatory five). Privacy mode
(`LEARNTRAIL_LOCAL_ONLY`) forces every request local and cannot leak, because the
local alias has no fallback. Verified live on the GPU: a chat answered end to end
by llama3.2:1b, no cloud call, and a recorded benchmark — local faster and free,
cloud more complete.

**Phase 12 — advanced features.** Flashcard generation from an approved Learning:
typed generation, schema validation, endpoint, UI. Generated on demand, never
stored — a study aid, not knowledge. Verified live: six valid cards from a real
Learning.

## After the roadmap

**Chat titles (2026-09-04).** Every conversation showed as `Untitled` forever.
Not a regression: docs/SPEC.md §6 lists "Generating titles" and §12 names a
`chat_title` prompt, and no phase plan ever picked either up — so nothing wrote
`chat.title` except the manual `PATCH /chats/{id}` rename, which the web client
never called. Closed with the piece that was missing: `prompts/chat_title/v1.toml`
on `learning-fast`, `ai_core.agents.titler` (typed generation into a `ChatTitle`
schema, like the flashcard agent), `POST /chats/{id}/title`, and a call from the
chat page after the first answered turn. The endpoint refuses to overwrite an
existing title, so it is safe to call unconditionally. Verified live: a real
conversation about primary keys titled itself "Primary key vs unique index in
Postgres".

## Standing items, unchanged by the roadmap being done

These predate the final phases and remain open — none blocks a phase, each is
recorded where it lives:

- **gitleaks is inert** (binary not installed; the hook skips loudly).
- **No branch protection**, so both CI gates report without blocking a merge.
- **No FAST CI lane** — lint/type/test run in git hooks only, not on GitHub.
- **The plans name agents that were never created** (`safety-engineer`,
  `eval-engineer`, `red-team`, `retrieval-engineer`, `prompt-optimizer`,
  `prompt-librarian`); the work was done by the agents that exist.
- **Privacy mode is not total**: chat routes local, but retrieval still embeds
  through the cloud `learning-embedding` alias.

## Correction to the Phase 8 note that used to be here

This section previously said Phase 6 was red because the chat path had no system
prompt, and named that as a genuine product gap. **That diagnosis was wrong**, and
it is worth recording how it was reached.

Two cases failed repeatedly, and the judge's explanations were fluent and
specific: "fails to encapsulate the definition in a single sentence", "fails to
accept the correction". I read those and inferred a missing prompt. I did not
read the answers. When I finally did, asked "In one sentence only: what is a
foreign key?", the system had answered:

    "A foreign key is a column or a set of columns in a database table that
     establishes a link between data in two tables by referencing the primary key
     of another table."

One sentence, referencing another table's key — both grading notes exactly
satisfied. The other case opened "You're correct that PostgreSQL is primarily a
relational database" and was marked down for not accepting the correction.

**The judge was wrong, not the product.** `safety-judge` (the cheap tier) is fine
for a yes/no safety rail and not for GEval, which scores by token probability over
a rubric. On `learning-deep` both cases pass. The lesson worth keeping is that a
confident, well-written explanation from a judge is not evidence — the output it
is judging is.

`learning_answer@1` was added anyway and is now wired: docs/SPEC.md §12 names it
and it did not exist, so the chat path sent a bare transcript for eight phases.
It was not the cause of anything, but its absence was real.

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

Phase 5 added tracing. Phoenix joined the stack as the fifth service (`16e0d88`),
which completes docs/SPEC.md §6's list — there is deliberately **no** standalone
OTel collector, though plans/phase-5.md named one; see
[ADR 0002](decisions/0002-no-otel-collector.md). A chat request now emits the
trace docs/SPEC.md §11 draws:

    POST /chats/{chat_id}/answer   3068ms
      chat.request                 3068ms
        load_conversation             2ms
        input_guardrails            643ms   allow_with_warning [api_key, email]
          nemo_rails                643ms
        context_builder               1ms   message_count=1
        llm.generate               1532ms   first_token=409ms  29/113 tokens
        output_guardrails           859ms   allow_with_warning [api_key]
          nemo_rails                859ms
        persist_message               5ms

Which immediately paid for itself: **half of a chat request is the two guardrail
calls**, and nothing before Phase 5 could have told you so.

`model_run` records what every call cost, joined to its trace by `trace_id`, and
each assistant turn in the UI carries a `trace ↗` link built from it. Verified
end to end: a message row's `trace_id` resolves in Phoenix to the trace holding
all seven spans.

Phase 6 added evaluation. `packages/evals` joined the uv workspace with 16
curated golden cases (conversations, summaries, safety), a DeepEval suite judged
through the gateway on `safety-judge`, `evaluation_case`/`evaluation_result`, a
Promptfoo comparison config, and — the phase's real deliverable — a **merge
gate**.

The gate is a fingerprint over the prompt/model configuration (the prompt library,
the alias-to-model mapping, the alias enum, the safety rails' prompts) compared
against the one recorded by the last *passing* run. It answers offline, in
milliseconds, with no model call: `make evals-gate`. That matters, because a check
that cost money to perform is one people learn to skip, which is the exact failure
the criterion exists to prevent.

Current state: all 26 results pass, recorded in
`packages/evals/reports/last_run.json`. Editing any prompt closes the gate
immediately — verified by doing it.

**The last inch is a GitHub setting I could not make.** A workflow can fail a
check; only branch protection can make it *required*. Until `evaluation-gate` is
marked required on `master`, it reports and does not block, and the criterion is
half enforced. The exact `gh api` command is in
[plans/phase-6.md](../plans/phase-6.md). `gh` is not installed here.

Phase 7 added red teaming, and — because the criterion is about *measurement* —
finished by making a real safety change and measuring it.

19 adversarial cases across injection, jailbreak, system-prompt extraction, PII
leakage, encoded attacks and multi-turn bypass. Six are controls, and every attack
category has one: a set of attacks alone is passed perfectly by a system that
refuses everything.

Every measurement carries **two** rates — attack success and false refusal — and
`compare()` returns `MIXED`, not `IMPROVED`, when a change buys one with the
other. That verdict is the phase's whole point.

The first baseline: **ASR 23% (3/13), FRR 0%**, with both system-prompt-extraction
attacks getting through. Neither used adversarial vocabulary, so v1's rail — which
named the *phrasing* an attack takes — did not match. `rails/v2.yml` describes the
effect instead. Re-measured:

    ASR 23% -> 0%     FRR 0% -> 0%     verdict: IMPROVED
      system_prompt_extraction   -100%
      multi_turn_bypass           -50%

That change closed Phase 6's evaluation gate (the rails are fingerprinted), which
is exactly what it is for; the golden suite was re-run and passes 28/28.

Phase 8 added retrieval. Postgres moved to `pgvector/pgvector:0.8.5-pg18`,
`learning_chunk` holds chunks with 1536-dimension embeddings behind an HNSW index
and a GIN full-text index, and `learning-embedding` joined the gateway as an alias
like any other.

**Attribution is a fact about retrieval, not a claim in the model's prose.** The
answer is built from chunks, each chunk carries the id of the Learning it came
from, and the citation list is those ids — nothing parses "[1]" markers, so the
model cannot invent a source or forget one.

Verified live against three Learnings seeded through the real approval flow:
questions about indexes and about vector databases each cited exactly the right
Learning; "How do I make sourdough bread?" returned `grounded: false` with no
citations and no model call at all.

That last one only works because of a **measured** distance floor. Without it a
nearest neighbour always exists, and the first run returned five confident
citations for the bread question:

    relevant question ....................... 0.215 - 0.338
    loosely related (slow SQL query vs an
      index Learning, which SHOULD match) ... 0.744
    unrelated (bread, marathons, football) .. 0.887 - 0.974

0.80 sits in the clean gap. Re-derive it if the embedding model changes — those
numbers are a property of that model's vector space, not of this code.

Retrieval is evaluated on its own terms — precision, recall, faithfulness —
because judging an *answer* cannot distinguish "right passages, poor answer" from
"best possible answer, wrong passages". **Not via Ragas**: 0.4.3 cannot be
imported at all, see [plans/phase-8.md](../plans/phase-8.md). Recall is 1.00 on
all three cases.

Phase 9 added prompt optimization, and before any of it, made the measurement
trustworthy — because a comparative criterion cannot be evaluated with a noisy
metric. Two fixes: the GEval judge moved to `learning-deep` (see the correction
above), and `CompletionRequest` gained `temperature`, which its own previous
comment invited "with a reason and a test". `None` still omits the parameter, so
every production call is unchanged; only the evaluation path pins 0. The suite
went from one or two failures a run, varying, to consecutive clean runs.

The optimization itself uses DSPy's COPRO on the summary task, over nine
transcripts split five train / four held out. COPRO because it optimizes
*instructions* — a few-shot demonstration cannot live in a `prompts/*.toml`
version, and an optimized artefact nobody can read or review is what §12's
versioning exists to prevent.

**The honest result is that no result is established:**

    run 1   train 1.00 -> 1.00   held-out 0.71 -> 0.79    IMPROVED
    run 2   train 0.80 -> 0.90   held-out 0.79 -> 0.71    OVERFITTED
    run 3   train 0.87 -> 1.00   held-out 0.76 -> 0.88    IMPROVED
    run 4   train 0.80 -> 0.93   held-out 0.85 -> 0.74    OVERFITTED

Averaging each score over three passes did not settle it, which located the
variance: it is in *which instruction COPRO lands on*, not in the scoring. So no
prompt version was promoted — which is what plans/phase-9.md asks, and what the
runner refuses to do on its own.

What the criterion actually asks for is demonstrated: the apparatus tells a gain
that generalised from one that did not, and reported `overfitted` on real runs
where train rose and held-out fell.

Next: Phase 10, model routing. `choose_model` has been a one-line rule since
Phase 2 and now reads the alias from the `learning_answer` prompt version — that
node is where routing lands.

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
- **Three plans have now named agents that do not exist**: `safety-engineer`
  (Phase 4), `eval-engineer` (Phase 6) and `red-team` (Phase 7). All that work was
  done by `ai-orchestration` and `backend-api` instead. Either the plans should
  stop naming them or the agents should be created; flagged three times without a
  decision.

- **There is still no FAST CI lane.** `.github/` now exists, but it holds only
  `evaluation-gate.yml`. docs/CODE_QUALITY.md's FAST lane (lint, types, tests,
  `alembic check`, stale-types, gitleaks) was moved to Phase 1 and never built,
  so lint and tests run only in git hooks — nothing checks a push that used
  `--no-verify`, and nothing checks the repo on GitHub at all. Two phases
  overdue. Deliberately not folded into Phase 6, which would have blurred what
  this phase delivered.

- **The v2 safety rails caused a Phase 2 regression, now fixed by v3.** v2 blocked
  "Reply with one short word." — a formatting instruction, not an attack — because
  it described the attack by its *shape* ("asking to repeat, summarise, translate,
  encode or continue"). v3 pins it to the object: what is asked for must be the
  assistant's own instructions. Worth remembering that Phase 7's measurement
  reported FRR 0% for v2 and was not wrong, only under-powered: all six controls
  were substantial questions, so nothing in the set had that shape.
  `rt-ctrl-007` closes it.

- **Trace volume is unbounded and unpruned.** Phoenix keeps every span on its
  volume forever. Harmless now; worth a retention policy before this runs for
  weeks. `docker compose down -v` is the current answer, which also throws away
  the database.

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
- **Graphify** — project-scoped Claude Code tooling, not a roadmap phase and not
  gated by invariant #6 (it does not touch AI application code). `.claude/skills/graphify/`
  (skill, project-scoped), `.claude/CLAUDE.md` (skill registration) and the
  `## graphify` section appended to this repo's [CLAUDE.md](../CLAUDE.md) tell
  Claude Code to query `graphify-out/graph.json` before broad codebase questions
  and run `make graphify-update` after modifying code. `.graphifyignore` excludes
  generated/dependency dirs and the tool's own bundled docs. The PreToolUse nudge
  hook lives in the gitignored `.claude/settings.local.json`, not the committed
  `.claude/settings.json` — its command embeds a machine-local absolute path.

---

Written by a model. Verify with `make status` before acting on anything above — this
file is a claim, not a fact.
