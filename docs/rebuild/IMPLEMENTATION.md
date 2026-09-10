# Nuroli Implementation Plan

Status: **Phase 2 complete and approved by the product owner.** Design authority:
[ARCHITECTURE.md](ARCHITECTURE.md) (decisions R-01 to R-39, contracts in
sections 4 to 23) and [DESIGN.html](DESIGN.html) (screens, states, tokens).
Nothing in this file is implemented. Phase 3 (development setup) and feature
implementation each require explicit authorization.

Branch: `rebuild/v1`. Integration branch for all implementation work: `rebuild/v1`
(I-01). This branch contains only the three planning files until Phase 3 begins.

## How an agent uses this document

Read only what the ticket needs (progressive disclosure):

1. `AGENTS.md` at the repository root (created in NU-001): commands and the
   short list of rules that apply to every change.
2. Section 2 of this document: coding and DDD rules for the layer you touch.
3. Section 4: your role's workflow and the evidence you must report.
4. Your ticket in section 8, plus the ARCHITECTURE.md and DESIGN.html sections
   it cites. Nothing else.

A ticket is the unit of work. One ticket, one branch, one pull request, one
reviewer. If anything in the ticket conflicts with ARCHITECTURE.md, stop and
ask (section 4.7); do not decide.

---

## 1. Purpose

Provide implementation instructions explicit enough that smaller, cheaper models
can execute them through OpenCode or any comparable agent, and that a human can
verify without trusting the agent's own report. The product owner makes product
and architecture decisions. Agents implement, test, and report.

Priority order when trade-offs arise: a working vertical slice, then security,
then tests, then code quality, then breadth. Never trade the first two for the
last.

---

## 2. Repository and coding rules

### 2.1 Deterministic repository commands

All work runs through `make` targets so agents, humans, and CI execute the same
thing. The root `Makefile` holds only `help` and `include make/*.mk`; targets
live in `make/backend.mk`, `make/frontend.mk`, `make/infra.mk`,
`make/agents.mk`, and `make/graph.mk` so tickets in different areas never edit
the same file.
Targets are declared in NU-001 and must never require a global tool other than
`make`, `docker`, `uv`, `pnpm`, and `git`. Every target honours the worktree
environment file described in section 4.3, so two worktrees can run stacks and
tests at the same time.

| Target | Runs |
| --- | --- |
| `make setup` | `uv sync` in `backend/`, `pnpm install --frozen-lockfile` in `frontend/`, `pre-commit install` |
| `make dev` | Compose dev stack: `db`, `api` with reload, Vite dev server with `/api` proxy, fake model container |
| `make up` / `make down` | Release stack from `compose.yaml` |
| `make fmt` / `make fmt-check` | Ruff format and Prettier write / check |
| `make lint` | Ruff lint, import-linter boundaries, ESLint |
| `make typecheck` | Pyright, `tsc --noEmit` |
| `make test-unit` | Backend unit tests (no database, no network) |
| `make test-integration` | Backend tests against PostgreSQL from the dev stack |
| `make test-contract` | Adapter contract tests against recorded fixtures |
| `make test-fe` | Vitest |
| `make e2e` | Playwright against the Compose test stack with the fake model |
| `make migrate` | `alembic upgrade head` |
| `make migration name=<slug>` | Autogenerate a migration for review |
| `make migrate-check` | `alembic check` (no drift) plus upgrade and downgrade round trip on an empty database |
| `make audit` | `pip-audit`, `pnpm audit --audit-level=high`, `gitleaks detect` |
| `make check` | `fmt-check lint typecheck test-unit test-integration test-contract test-fe migrate-check` — the local equivalent of the pull-request gate; starts this worktree's `db` container if it is not running |
| `make deps-update` | `uv lock --upgrade` and `pnpm update --latest` within manifest ranges, then `make audit check`; run weekly by the owner and committed under the owner's identity (R-40) |
| `make backup` / `make restore FILE=` | `pg_dump -Fc` into `backups/` / restore into a stopped stack |
| `make check-model` | Runs `nuroli check-model` inside the API container |
| `make worktree T=NU-0nn` | Creates `../nuroli-NU-0nn` worktree on branch `ticket/NU-0nn-<slug>` from `rebuild/v1`, copies `.env` (or `.env.example` with development defaults), writes `.worktree.env` with the project name, port offsets, and the baseline (`BASE_COMMIT`, `BASE_SCHEMA_HEAD`), and builds the code graph (section 4.3) |
| `make graph-build` | Full code-graph rebuild: removes `graphify-out/` and runs `graphify update .` (AST only, no LLM); `FORCE=1` allowed after refactors that delete code |
| `make graph-update` | Incremental `graphify update .`; refuses to shrink the graph unless `FORCE=1`; runs automatically after every commit through the post-commit hook |
| `make graph-watch` | `graphify watch .` in the foreground for a live session (optional, for a Herdr pane) |
| `make graph-impact BASE=<ref>` | `scripts/graph_impact.py`: changed files against `BASE` (default `origin/rebuild/v1`) → changed nodes and communities → affected nodes outside the changed files (reverse traversal, depth 2) and god nodes touched; writes `graphify-out/impact.md` |
| `make graph-conflicts` | `scripts/graph_conflicts.py`: for every other `origin/ticket/*` branch, intersects its changed and affected node sets with this branch's; writes `graphify-out/conflicts.md` |
| `make graph-overlap A=<paths> B=<paths>` | Same script in planning mode: community overlap between two ownership boundaries before a lane is opened |
| `make preflight` | Fetches `origin/rebuild/v1`; fails if the branch is not rebased on it; compares `BASE_COMMIT` and `BASE_SCHEMA_HEAD` with the current head and Alembic head and reports "baseline moved"; runs `graph-update`, verifies `built_at_commit` equals `HEAD` with a clean tree, then `graph-impact` and `graph-conflicts`; writes `graphify-out/preflight.md` for the pull request evidence |

Every target prints the exact commands it runs. A target that cannot run its
tool fails with a non-zero exit and a one-line reason; it never silently skips.

### 2.2 Clean-code rules (enforced by tools where possible)

- Functions do one thing; Ruff `C901` complexity limit 10, `PLR0913` max 6
  arguments. Modules under 400 lines; split by responsibility, not by size.
- Names say what a thing is: `confirm_summary`, not `process`. Booleans read as
  predicates: `is_active`, `research_requested`.
- No dead code, no commented-out code, no TODO without a ticket id.
- No global mutable state except the rate limiter and concurrency slots in
  `platform`, which are explicitly documented.
- Errors are typed: domain errors subclass `DomainError` in `shared_kernel`;
  the API layer maps them once. Never catch `Exception` except at the HTTP
  boundary and the streaming generator.
- Type hints everywhere in Python; Pyright `strict` on `domain` and
  `application` packages, `standard` elsewhere. TypeScript `strict` with
  `noUncheckedIndexedAccess`.
- Tests describe behavior: `test_confirm_requires_matching_revision`, not
  `test_confirm_2`. No test asserts on private attributes or call counts of
  internal helpers.
- Comments explain why, never what. Docstrings only on public use cases and
  ports.

### 2.3 DDD implementation rules

**Module organization.** `backend/src/nuroli/<module>/{domain,application,infrastructure,api}`
for `identity`, `conversations`, `knowledge`. `platform`, `shared_kernel`, and
`adapters` are flat packages. `import-linter` contracts (NU-006) enforce:

- `domain` imports only the standard library, `shared_kernel`, and its own
  module's `domain`.
- `application` imports `domain`, `shared_kernel`, `ports`, and other modules'
  `application` packages; never `infrastructure`, `api`, FastAPI, SQLAlchemy,
  Pydantic, or httpx.
- `infrastructure` imports `domain`, `application` (for protocols), `platform`,
  SQLAlchemy, httpx.
- `api` imports `application` and `platform`; never `infrastructure` directly
  except through dependency providers in `platform`.
- One module never imports another module's `domain`, `infrastructure`, or
  `api`. Cross-module reads go through a port defined by the consumer and
  implemented by the provider (example: `ConversationTranscriptPort`); the
  composition root `platform/wiring.py` connects them.
- Each module exposes exactly one `api/router.py`; `main.py` includes the three
  module routers and the platform routers once (NU-006) and is not edited by
  feature tickets. Startup and shutdown behavior lives in `platform/lifespan.py`.

**Aggregates enforce invariants.** State changes happen through aggregate
methods (`conversation.start_reply(...)`, `summary.confirm(revision, now)`)
that raise domain errors. Repositories persist whatever the aggregate holds;
they never validate. Use cases never mutate aggregate fields directly.

**Persistence mapping.** SQLAlchemy models live in `infrastructure/models.py`
and are never returned by repositories. `infrastructure/mappers.py` has
`to_domain(row) -> Aggregate` and `apply(aggregate, row)` functions. New
messages and versions are detected by comparing ids present on the aggregate
with ids loaded, tracked in a private `_new_*` list on the aggregate that the
repository clears after save.

**Ports and repositories.** Shared ports `ChatModelPort` and `WebSearchPort`
live in `nuroli/ports/`. Module-specific ports and repository protocols live in
that module's `application/ports.py`; repository implementations in
`infrastructure/repositories.py`. Every method that reads an owned aggregate
takes `owner_id` and filters in SQL. Methods exist only when a use case calls
them.

**Transactions.** `platform/db.py` provides `UnitOfWork` wrapping one
`AsyncSession`. A FastAPI dependency opens it per request; use cases receive
it and call `await uow.commit()` at the end. Streaming use cases commit after
creating message rows and again after finalizing. No transaction spans two
aggregates, except confirm, which updates the summary row and its own
`search_vector` column.

**Use cases through FastAPI.** Each use case is a class with an `async def
execute(self, input: XInput) -> XOutput`. Routers build the input from the
Pydantic request plus `current_user`, call `execute`, and map the output to the
response schema. Routers contain no branching on domain state.

**Frontend features map to use cases.** `frontend/src/features/<feature>/api.ts`
has one function per endpoint returning types declared in that feature's
`types.ts`; components call TanStack Query hooks in `hooks.ts` that wrap those
functions. `frontend/src/api/` holds only the shared transport (`client.ts`,
`sse.ts`, `errors.ts`). No component calls `fetch` directly.

**Testing without external services.** Domain tests construct aggregates and
call methods. Use-case tests use in-memory repository fakes
(`tests/unit/<module>/fakes.py`) and `FakeChatModel` / `FakeWebSearch` from
`adapters/fakes.py`. Integration tests use the real PostgreSQL. Contract tests
use `respx` with fixtures in `tests/contract/fixtures/`. End-to-end tests use
the fake model container and never a paid endpoint.

**Avoiding needless abstraction.** Add a class, base class, generic, or
indirection only when a second concrete use exists in the same ticket or in
ARCHITECTURE.md. No "manager", "helper", "utils", or "common" modules. No
plugin registries. No event bus. A reviewer rejects speculative abstraction.

**Vertical slice first.** Every phase ends with something a user can do through
the browser against the real API. Broad infrastructure without a slice using it
does not merge.

### 2.4 Naming and module-boundary rules

- Python: `snake_case` modules and functions, `PascalCase` classes, `UPPER_CASE`
  constants. TypeScript: `camelCase` functions, `PascalCase` components and
  types, `kebab-case` file names except components (`PascalCase.tsx`).
- Use-case names are verbs: `RegisterUser`, `SendMessage`, `ConfirmSummary`.
- API schemas end with `Request` or `Response`. Domain objects carry no suffix.
- Frontend features: `auth` (identity module), `conversations` (conversations
  module), `summaries` and `knowledge` (both map to the knowledge module:
  capture screens and the ask screen).
- No file named `types.py` or `models.ts` outside the documented locations.

### 2.5 Dependency and version rules

- `uv.lock` and `pnpm-lock.yaml` are the only sources of truth; commits that
  change them touch nothing else except the manifest and are reviewed
  separately (serialized ownership, section 4.4).
- Pin direct dependencies with compatible ranges in manifests; lockfiles pin
  exact versions. Docker base images pinned by tag and digest.
- A new dependency needs a one-line justification in the pull request and must
  pass `make audit`. Prefer the standard library.
- Dependency updates happen only through `make deps-update`, run and committed
  by the owner (R-40); agents do not bump versions inside feature tickets.

### 2.6 Environment and configuration rules

- All configuration through `NUROLI_*` environment variables read once by
  `platform/settings.py`; nothing reads `os.environ` elsewhere.
- `.env.example` lists every variable with a placeholder and a comment; adding a
  variable without updating it fails review.
- Settings validation fails fast at start with all problems listed.
- Tests set configuration through fixtures, never by editing `.env`.

### 2.7 Secret-handling rules

- No secret in the repository, in images, in logs, in test fixtures, in pull
  request text, or in agent reports. `gitleaks` runs in pre-commit and CI.
- Development uses the fake model container by default; a real key is optional
  and lives only in the developer's local `.env`.
- Agents never receive production credentials. CI has no provider keys.
- Error messages and the capabilities endpoint never include configuration
  values other than the model name.

### 2.8 Rules against over-engineering

Do not add: background workers, message queues, caching layers, feature flags
frameworks, multi-tenancy beyond `owner_id`, generic CRUD bases, GraphQL, ORM
events, custom middleware beyond request id, CSRF, and rate limiting, a second
model protocol, embeddings, page fetching, admin UI, i18n frameworks, state
management libraries, CSS frameworks, or component libraries. Each of these is
either deferred in ARCHITECTURE.md section 1.4 or unnecessary. A ticket that
seems to need one stops and asks.

---

## 3. Tool workflow rules

### 3.1 OpenCode

- Project agents live in `.opencode/agents/implementer.md` and
  `.opencode/agents/reviewer.md` (NU-005). Implementer: `mode: primary`,
  `permission.edit: allow`, `permission.bash: allow`. Reviewer: `mode: primary`,
  `permission.edit: deny`, `permission.bash: allow` (to run `make` targets),
  `permission.write: deny`.
- Model ids are set in the developer's local OpenCode config or environment,
  never in committed files. Committed agent files set only role, prompt, and
  permissions.
- `AGENTS.md` is the only instruction file OpenCode loads automatically. It
  points to sections of this document; it does not duplicate them.
- Each OpenCode session works in exactly one worktree and one ticket.
- Skills: none required. If a project skill is ever added it follows the
  `SKILL.md` format and is optional.

### 3.2 OpenRouter

- Optional gateway for agent models. Set the account privacy setting to deny
  data collection by providers. Use per-project keys with spending limits.
- Any OpenAI-compatible endpoint (local runtime, another gateway, a vendor API)
  may replace it without repository changes.
- The application under development does not depend on OpenRouter either; the
  fake model container is the default for development and tests.

### 3.3 Herdr

- Optional. Use it to run up to two implementer sessions and one reviewer
  session in separate panes and worktrees, and to see which is blocked.
- Create worktrees with `make worktree T=NU-0nn`, not with Herdr's own
  shortcut, so branch names follow section 4.3.
- No automation is built on Herdr's socket API. The workflow must be identical
  in plain terminals.

### 3.4 Model-agnostic expectations

Every instruction in this document is executable by any agent or human who can
run `make`. Verification is a command with an expected exit code and output,
never a model's opinion. Reports quote command output.

### 3.5 Graphify (R-41)

Graphify keeps a code knowledge graph of `backend/`, `frontend/`, and `infra/`
in `graphify-out/` (git-ignored, rebuilt per worktree, deterministic AST
extraction, no LLM). The graph informs; git, migrations, and tests decide.

1. **Split work by low-overlap communities.** Before the integrator opens a
   parallel lane (section 4.9), `make graph-overlap A=<paths of ticket A>
   B=<paths of ticket B>` must show no shared community with more than a
   handful of nodes; otherwise the tickets run sequentially. Tickets still name
   files and modules, never community ids, because communities are an analysis
   output that can change as code grows. Each agent works in its own worktree
   and branch (section 4.3).
2. **Single writer for shared critical resources.** Migrations, `ports/`,
   `shared_kernel/`, API schemas, Compose files, workflows, and the root
   `Makefile` have one open ticket at a time (section 4.4). A ticket that needs
   a change there depends on the ticket that owns it; it never edits those
   files concurrently and never asks the graph to arbitrate.
3. **Refresh, then re-check the baseline before writing and before merging.**
   The post-commit hook runs `make graph-update` after every commit, and
   `make graph-watch` may run in a pane during a session. Before opening or
   updating a pull request, `make preflight` re-fetches `rebuild/v1`, compares
   the worktree's recorded `BASE_COMMIT` and `BASE_SCHEMA_HEAD` with the
   current head, and refreshes the graph. If the baseline moved, the
   implementer rebases, re-runs `make check`, and runs `make preflight` again.
   The reviewer repeats `make preflight` on the branch head.
4. **Impact and conflict analysis before merge, tests as the gate.** Preflight
   writes `graphify-out/impact.md` (nodes outside the changed files that are
   affected, communities and god nodes touched) and `graphify-out/conflicts.md`
   (overlap with other open ticket branches). Both go into the pull request
   evidence. A non-empty conflict report requires the integrator to merge the
   tickets in dependency order and the later one to rebase and re-verify. CI's
   `graph` job rebuilds the graph from scratch and fails only when the graph
   is unbuildable or unhealthy. No merge is blocked by the graph alone.

Agents use the graph to answer codebase questions cheaply: `graphify query
"<question>"`, `graphify explain "<node>"`, `graphify path "A" "B"`, and
`graphify god-nodes`. Claude Code sessions may also use the `/graphify` skill;
OpenCode sessions use the CLI only. A docs-plus-code graph (LLM semantic
extraction of `docs/rebuild/`) is optional and built only by the owner in the
main checkout; it is never required by a ticket.

---

## 4. Agent roles and workflow

### 4.1 Roles

**Planner.** Converts an approved phase into tickets in this document, keeps
them dependency-ordered, and records decisions. Does not write code. In Phases
1 and 2 the planner is the assistant session working with the product owner.
During implementation the planner re-slices a ticket only when an implementer
stops and asks.

**Implementer.** Takes one ticket, works on its branch in its worktree, changes
only files inside the ticket's ownership boundary, writes the required tests,
runs the verification commands, and opens a pull request with the report in
section 4.6.

**Reviewer.** A different agent (and a different model when both are models)
with edit denied. Reads the diff, runs the verification commands, checks every
item in the ticket's acceptance criteria and definition of done, checks
architecture alignment (layers, boundaries, invariants, ownership), security
requirements, reliability requirements, and code quality, and posts the review
evidence in section 4.6. Approves or requests changes. No ticket is complete
without this evidence.

**Integrator.** The product owner merges approved pull requests into
`rebuild/v1` in ticket order with a local fast-forward after rebase (R-40).
Agents do not merge, and the GitHub merge button is not used.

### 4.2 Assignment rules

- A ticket is assigned only when every ticket in its Dependencies is merged.
- At most two implementers run concurrently, on tickets with disjoint
  ownership boundaries, no shared serialized files (section 4.4), and no
  significant community overlap in `make graph-overlap` once a code graph
  exists (section 3.5).
- The reviewer for a ticket is never its implementer.
- Tickets marked `not ready` are never assigned.

### 4.3 Branch and worktree isolation

- `make worktree T=NU-0nn` creates branch `ticket/NU-0nn-<slug>` from the
  current `rebuild/v1` in `../nuroli-NU-0nn`.
- One branch per ticket; rebase on `rebuild/v1` before opening the pull
  request; no merges from other ticket branches.
- Commits follow Conventional Commits with the ticket id:
  `feat(conversations): NU-026 stream replies over SSE`. Types: `feat`, `fix`,
  `chore`, `docs`, `test`, `refactor`. Pull request title equals the ticket
  title. CI checks the branch name and commit subject with a regex (NU-004).
- Every commit is authored and committed under the repository owner's git
  identity (R-40). Agents use the identity already configured in git; they never
  set `user.name` or `user.email`, never pass `--author`, and never add
  `Co-Authored-By` or `Signed-off-by` trailers. The `conventions` job rejects
  violations.
- Each worktree is isolated at runtime: `make worktree` writes `.worktree.env`
  (git-ignored) with `COMPOSE_PROJECT_NAME=nuroli-nu<nnn>` and port offsets
  derived from the ticket number `n`: web `8080+n`, API `8000+n`, PostgreSQL
  `5432+n`, Vite `5173+n`, fake model `9000+n`. Every Compose file and
  Playwright config reads these variables, so two agents can run `make dev`,
  `make test-integration`, and `make e2e` at the same time without port or
  volume collisions. The main checkout uses offset 0.
- `.worktree.env` also records the baseline: `BASE_COMMIT` (the `rebuild/v1`
  commit the branch started from) and `BASE_SCHEMA_HEAD` (the Alembic head at
  that commit). `make preflight` compares both with the current integration
  head and reports "baseline moved" when either changed (section 3.5).
- `make worktree` builds the code graph for the new worktree so the first
  `make preflight` and any `graphify query` work immediately.
- Worktrees are removed after merge (`git worktree remove`), which also stops
  and removes that worktree's Compose project (`make worktree-clean T=NU-0nn`).

### 4.4 File ownership

Each ticket lists the paths it may change. Anything else is out of bounds; if a
change outside the boundary is unavoidable, stop and ask.

Serialized ownership (one open ticket at a time; reviewer must confirm no
concurrent ticket touches them): `backend/migrations/`, `backend/pyproject.toml`,
`backend/uv.lock`, `frontend/package.json`, `frontend/pnpm-lock.yaml`,
`backend/src/nuroli/shared_kernel/`, `backend/src/nuroli/ports/`, any
`application/ports.py`, API schemas (`*/api/schemas.py`), `frontend/src/api/`,
`compose*.yaml`, `infra/`, `.github/`, `AGENTS.md`, the root `Makefile`,
`docs/rebuild/*`.

Area-owned files that parallel tickets may edit without serialization because
no two areas share them: `make/backend.mk`, `make/frontend.mk`, `make/infra.mk`,
`make/agents.mk`, `make/graph.mk` (graph targets belong to the agents area); each module's own packages and tests; each frontend feature
directory; `.github/workflows/<area>.yml` when the ticket is the only open one
in that area.

Migrations carry a sequential file prefix (`0002_`, `0003_`) and an Alembic
revision chain. Because they are serialized, two heads cannot occur; if a rebase
ever produces two heads, `make migrate-check` fails and the later ticket
renumbers before merge.

### 4.5 Stop-and-ask rules

An agent stops, writes what it found and what it needs, and waits when:

- the ticket requires a change to a decision in ARCHITECTURE.md section 3 or a
  contract in sections 6, 7, 10, 11, or 16;
- a required file is outside the ownership boundary;
- a dependency ticket's output does not match what this ticket assumes;
- a verification command fails for a reason unrelated to the ticket;
- a security requirement cannot be met as specified;
- a needed library, tool, or credential is unavailable.

Never work around by weakening a test, skipping a check, or adding a flag.

### 4.6 Handoff and evidence

The implementer's pull request description and the reviewer's review contain,
under fixed headings:

1. **Ticket:** id and title.
2. **Files changed:** list, each inside the boundary.
3. **Commands run:** exact commands with exit codes.
4. **Results:** pasted tails of test output including counts.
5. **Acceptance criteria:** each criterion with how it was verified.
6. **Limitations:** anything not done or not verified.
7. **Follow-up risks:** what the next ticket should watch.
8. **Handoff:** the information the ticket's Handoff field asks for.
9. **Preflight:** the contents of `graphify-out/preflight.md` from the branch
   head (baseline status, impact summary, conflict summary), once NU-050 is
   merged.

The reviewer adds: **Boundary check**, **Architecture check** (layers,
invariants, ownership), **Security check**, **Reliability check**, **Impact
check** (the reviewer's own `make preflight` output and whether affected nodes
outside the ticket boundary are covered by tests), **Verdict**.

### 4.7 Avoiding duplicate or conflicting work

- The ticket list in section 8 is the single queue. Each ticket carries a
  **Status** line (`not started`, `in progress`, `in review`, `merged`,
  `blocked: <reason>`). The implementer sets `in progress` when the branch is
  created and `in review` when the pull request is opened; the integrator sets
  `merged`. This Status line is the only part of `docs/rebuild/*` an agent may
  edit, and the change is committed on the ticket's own branch (`docs: NU-0nn
  status <value>`) so it merges with the ticket.
- Before starting, an implementer runs `git fetch` and confirms no open pull
  request carries the same ticket id.
- Two tickets never share a file in the same window unless one is merged.

### 4.8 Secrets and permissions

Production secrets exist only in the operator's `.env` on the deployment host.
Agents and CI use throwaway values and the fake model container. The release
workflow has package-write permission only; all other jobs are read-only.

### 4.9 Parallel lanes

Tickets whose dependencies are merged and whose ownership boundaries are
disjoint may run at the same time. The pairs below are the intended lanes; the
integrator may open others when both conditions hold.

| Lane A | Lane B | Shared files | Note |
| --- | --- | --- | --- |
| NU-002 backend toolchain | NU-003 frontend toolchain | none (`make/backend.mk` vs `make/frontend.mk`) | first parallel pair |
| NU-049 graph targets and hook | NU-006 backend module layout | none (`make/graph.mk` vs backend packages; `AGENTS.md` is serialized and NU-006 does not touch it) | |
| NU-050 impact and preflight | NU-009 settings and logging | none | |
| NU-007 shared kernel | NU-008 frontend shell | none | |
| NU-009 settings and logging | NU-008 frontend shell | none | |
| NU-012 identity domain | NU-010 Compose stacks | none | |
| NU-012 identity domain | NU-011 database foundation | none | |
| NU-015 Google sign-in | NU-016 frontend auth screens | none (NU-016 depends on NU-014 only) | Google path is not end-to-end tested |
| NU-017 operator commands | NU-016 frontend auth screens | none | |
| NU-020 chat port and fake | NU-019 password change and account screen | none | |
| NU-023 conversation domain | NU-021 model adapter | none | |
| NU-022 fake model container | NU-023 conversation domain | none | |
| NU-029 search port and adapter | NU-028 frontend conversations | none | |
| NU-032 knowledge domain | NU-030 research in SendMessage | none | |
| NU-032 knowledge domain | NU-031 frontend research | none | |
| NU-036 frontend library | NU-037 AskKnowledge backend | none | |
| NU-041 backup and recovery | NU-040 release workflow | none (`make/infra.mk` vs `.github/workflows/release.yml`) | |
| NU-043 security gates | NU-044 accessibility gates | none | |

Everything else is sequential. A reviewer session may run alongside any
implementer session at all times. From NU-050 onward, opening any lane pair
also requires a clean `make graph-overlap` for the two tickets' ownership
paths (section 3.5); lanes before that are judged by directory alone because
little code exists.

---

## 5. Quality gates

### 5.1 Pre-commit (installed by `make setup`)

Ruff format and lint on staged Python, Prettier and ESLint on staged frontend
files, `gitleaks protect --staged`, a check that `.env` is not staged, and, at
the `post-commit` stage, `make graph-update` (R-41). The pre-commit framework
is the only hook manager; `graphify hook install` is not used.

### 5.2 Pull-request gate (GitHub Actions, one workflow file per area, all required)

| Workflow | Job | Command | Purpose |
| --- | --- | --- | --- |
| `backend.yml` | backend-quality | `make fmt-check lint typecheck` (backend part) | Style, boundaries, types |
| `backend.yml` | backend-tests | `make test-unit test-integration test-contract` with a PostgreSQL 18 service | Behavior |
| `backend.yml` | migrations | `make migrate-check` | No drift; reversible |
| `backend.yml` | security | `make test-security` (from NU-043) | Security matrix |
| `frontend.yml` | frontend-quality | `make fmt-check lint typecheck` (frontend part) | Style, types |
| `frontend.yml` | frontend-tests | `make test-fe` | Components and hooks |
| `e2e.yml` | e2e | `make e2e` against the Compose test stack with the fake model | Journeys, accessibility (axe) |
| `audit.yml` | audit | `make audit` | Vulnerabilities and secrets |
| `conventions.yml` | conventions | branch regex, commit subject regex, author and committer identity, no co-author or sign-off trailers (R-40) | Traceability and identity |
| `graph.yml` | graph | `make graph-build` from scratch, health check, `make graph-impact BASE=origin/rebuild/v1`; report to job summary and artifact; fails only if unbuildable or unhealthy | Blast radius visible on every PR |

Merges into `rebuild/v1` require all jobs green plus one approving review that
contains the evidence headings.

### 5.3 Test categories and what each must prove

| Category | Location | Proves |
| --- | --- | --- |
| Unit | `backend/tests/unit`, `frontend/src/**/*.test.tsx` | Aggregate invariants, domain services, use cases with fakes, component states |
| Integration | `backend/tests/integration` | Repositories, migrations, endpoints with a real database, ownership isolation |
| Contract | `backend/tests/contract` | Adapters against recorded provider responses; SSE encoding against the documented event schema |
| End-to-end | `frontend/tests/e2e` | User journeys in DESIGN.html through the real stack with the fake model; keyboard and axe checks |
| Security | inside the above, tagged `security` | Cross-user 404 matrix, CSRF, cookie flags, throttling, sanitization, prompt-injection fixtures, secret absence in logs |

No coverage percentage is enforced (I-03). The reviewer verifies that each
ticket's required tests exist and test behavior.

### 5.4 Standard verification, definition of done, and reviewer evidence

Unless a ticket says otherwise:

- **Standard verification:** `make check` passes locally; the ticket's specific
  commands pass; `make e2e` passes when the ticket touches the frontend or an
  endpoint used by the frontend; `make preflight` passes on the branch head
  (from NU-050 onward).
- **Standard definition of done:** all acceptance criteria verified; required
  tests present and passing; no files outside the boundary; no new dependency
  without justification; `.env.example` and AGENTS.md updated when relevant;
  pull request evidence complete; reviewer approved.
- **Standard reviewer evidence:** commands re-run by the reviewer with output
  tails; boundary, architecture, security, and reliability checks written out;
  each acceptance criterion marked verified or not.

### 5.5 Release gate (`release.yml` on tag `v*`)

Build both images, run Trivy (fail on high or critical), push to GHCR with the
tag and digest, attach `compose.yaml` and `.env.example`, and run the upgrade
test (NU-045) from the previous tag.

### 5.6 Release and rollback checks

Before tagging: `make check`, `make e2e`, backup and restore drill
(`make backup`, `make restore`), upgrade from the previous tag on a copy of
real-shaped data, and review of every migration for reversibility. Rollback:
previous image tag plus restore only if a migration was destructive, which
requires its own ticket and product-owner approval.

### 5.7 Reliability and failure-recovery checks

Each phase's last ticket includes: container restart keeps data; API restart
during a stream leaves a `failed` message and a usable conversation; database
unavailable makes `/ready` return 503 and the UI show a recoverable error;
model endpoint down yields `model_unavailable` with retry.

---

## 6. Approved skills and practices catalog

Full evaluation in ARCHITECTURE.md section 22.3 (R-27). Usage boundaries:

| Practice | Use in tickets that | Do not use for |
| --- | --- | --- |
| AGENTS.md entry file | every ticket reads it | duplicating this document |
| OWASP ASVS 5.0 items and cheat sheets | touch auth, sessions, ownership, rendering, or external content | general code style |
| WCAG 2.2 AA with axe | touch any screen | backend-only tickets |
| FastAPI structure rules | create routers or schemas | domain code |
| Test-first for domain and use cases | create or change aggregates, domain services, use cases | adapters, UI, configuration |
| Adapter contract tests with recorded fixtures | create or change an adapter or the SSE encoder | domain code |
| Import-boundary lint | every backend ticket | frontend |
| Conventional Commits and ticket branches | every ticket | — |
| Graphify code graph (section 3.5) | lane planning, every preflight and review, codebase questions | deciding merges, replacing tests, tickets referencing community ids |

No third-party skill package is required or installed.

---

## 7. Process decision register

| ID | Decision | One-line reason |
| --- | --- | --- |
| I-01 | Integration branch is `rebuild/v1` until v1 is releasable; `master` receives one reviewed merge then. | Keeps `master` stable and the old code untouched until the rebuild works. |
| I-02 | Ticket ids `NU-001` upward; branches `ticket/NU-0nn-slug`; Conventional Commits with the ticket id; pull request title equals ticket title. | Deterministic names that CI can check. |
| I-03 | No numeric coverage gate; reviewers verify required tests per ticket. | Avoids tests written to satisfy a number. |
| I-04 | Phase 3 (NU-001 to NU-011) is executed by the assistant session that produced this plan, under the same evidence rules; feature tickets from NU-012 onward may go to OpenCode agents. | The harness must exist and be proven before weaker agents depend on it. |
| I-05 | Tickets carry every required field; fields that equal the standard in section 5.4 say "standard". | Keeps tickets complete without repeating boilerplate. |
| I-06 | Two implementers and one reviewer maximum; serialized files in section 4.4. | Modular monolith with shared schemas cannot absorb more parallel change safely. |
| I-07 | The fake model container is the default model for development and every automated test. | Tests run without paid calls and without keys. |
| I-08 | Release images publish to `ghcr.io/amirhosseinsaloot/nuroli-api` and `ghcr.io/amirhosseinsaloot/nuroli-web`. | Matches the repository owner. |
| I-09 | Conflict points for parallel agents are removed structurally: per-area Makefile includes, per-area workflow files, per-module routers registered once, per-feature frontend types, per-module test fakes, per-worktree Compose project names and ports. | Two implementers must be able to work without touching a shared file or port. |
| I-10 | Graphify is wired in through Make targets, a post-commit hook, `make preflight`, and a non-blocking CI graph job (section 3.5, R-41); ticket ids are stable and NU-049 and NU-050 sit in Phases 1 and 2 by dependency, not by number. | The graph must be current at every commit and consulted at every lane, preflight, and review without becoming a shared artifact or a gate. |

---

## 8. Ticket backlog

Ordered by dependency. Each ticket is small enough for one implementer and one
reviewer. Fields marked "standard" refer to section 5.4. Phases follow the
order required for the rebuild: foundation and authentication first. Ticket ids
are stable and never renumbered; a ticket added later keeps the next free id
and is placed in the phase its dependencies require (NU-049 and NU-050).

Ticket field key: **Phase** · **Context** (bounded context or platform) ·
**Objective** · **Outcome** · **Dependencies** (merged tickets) ·
**Prerequisites** (environment) · **Files** (may change) · **Ownership** ·
**Domain** (entities, value objects, aggregates, use cases) · **Contracts** ·
**Security** · **Reliability** · **Steps** · **Failure cases** · **Tests** ·
**Verify** · **Acceptance** · **Done** · **Reviewer evidence** · **Handoff** ·
**Reason** · **Practices** · **Status** (section 4.7).

### Phase 1 — Repository and development contracts

#### NU-001 Repository skeleton, AGENTS.md, Makefile contract, ignore rules
- **Phase:** 1 · **Context:** platform
- **Objective:** Create the root layout from ARCHITECTURE.md section 23 with a root `Makefile` (help plus `include make/*.mk`) and `make/backend.mk`, `make/frontend.mk`, `make/infra.mk`, `make/agents.mk` whose targets exist and fail loudly until later tickets implement them, `AGENTS.md`, `README.md` stub, `.gitignore`, `.editorconfig`, `.env.example` with every variable from ARCHITECTURE.md section 16.
- **Outcome:** Any agent can clone, read AGENTS.md, and run `make` to see the command contract.
- **Dependencies:** none · **Prerequisites:** Phase 3 authorized; `make`, `git`.
- **Files:** `AGENTS.md`, `CLAUDE.md`, `README.md`, `Makefile`, `make/*.mk`, `.gitignore`, `.editorconfig`, `.env.example`, empty `backend/`, `frontend/`, `infra/`, `scripts/` directories with `.gitkeep`.
- **Ownership:** serialized (root files).
- **Domain:** none.
- **Contracts:** Makefile target names from section 2.1; `.env.example` variable names from ARCHITECTURE.md section 16; `.gitignore` covers `.env`, `.env.*` except `.env.example`, `*.pem`, `*.key`, `*.crt`, `*.dump`, `backups/`, `*.log`, `node_modules/`, `.venv/`, `dist/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `playwright-report/`, `test-results/`, `.opencode/*.local.*`, `.agent-scratch/`, `.worktree.env`, `graphify-out/`.
- **Security:** no secret placeholders that look real; `.env` ignored before any `.env` can exist.
- **Reliability:** unimplemented targets exit 1 with "not implemented until NU-0nn".
- **Steps:** 1. Create directories. 2. Write Makefile with all targets from section 2.1, each echoing its commands; stub bodies exit 1 with the owning ticket id. 3. Write `.env.example` with placeholders and comments. 4. Write AGENTS.md: purpose, command table, the rules (ownership boundary, stop-and-ask, no secrets, tests required, layer boundaries, Conventional Commits, owner-only git identity with no trailers (R-40), evidence headings, no over-engineering, read only relevant sections, never edit planning docs except a ticket's Status line, one worktree per session, keep the code graph current and run `make preflight` before a pull request (R-41)), pointers to sections of this document and ARCHITECTURE.md. Also write a one-line `CLAUDE.md` containing `@AGENTS.md` so Claude Code sessions load the same rules. 5. Write README stub with install placeholder. 6. Write `.gitignore` and `.editorconfig`.
- **Failure cases:** `make` without a target prints help; unknown target fails.
- **Tests:** shell test `make help` exit 0; `make lint` exits 1 with the NU-002 message; `git check-ignore .env` succeeds.
- **Verify:** `make help`, `git check-ignore -q .env && echo ignored`, `grep -c NUROLI_ .env.example` (equals the variable count in ARCHITECTURE.md section 16).
- **Acceptance:** all targets listed; `.env` ignored; AGENTS.md under 150 lines; no secret-like strings (gitleaks clean once NU-004 lands).
- **Done:** standard · **Reviewer evidence:** standard plus confirmation that `.env.example` matches section 16 variable by variable.
- **Handoff:** list of stub targets each later ticket must implement.
- **Reason:** everything else depends on a deterministic command contract; a stubbed Makefile makes missing pieces visible instead of silent.
- **Practices:** AGENTS.md entry file.
- **Status:** merged

#### NU-002 Backend toolchain: uv, Ruff, Pyright, pytest
- **Phase:** 1 · **Context:** platform
- **Objective:** `backend/pyproject.toml` with Python 3.14, uv-managed dependencies (fastapi, uvicorn, pydantic-settings, sqlalchemy[asyncio], asyncpg, alembic, httpx, argon2-cffi, authlib, import-linter (logging uses the standard library with a JSON formatter); dev: pytest, pytest-asyncio, respx, ruff, pyright), Ruff and Pyright configuration per section 2.2, pytest configuration, and Make targets `fmt`, `fmt-check`, `lint`, `typecheck`, `test-unit` for the backend.
- **Outcome:** `make lint typecheck test-unit` run on an empty package.
- **Dependencies:** NU-001 · **Prerequisites:** uv installed.
- **Files:** `backend/pyproject.toml`, `backend/uv.lock`, `backend/src/nuroli/__init__.py`, `backend/tests/unit/test_smoke.py`, `make/backend.mk`.
- **Ownership:** serialized (`pyproject`, `uv.lock`); `make/backend.mk` is backend-area owned.
- **Domain:** none · **Contracts:** Ruff rules `E,F,I,B,UP,C90,PL,S` with `C901=10`; Pyright strict globs for `*/domain`, `*/application`, `shared_kernel`.
- **Security:** Ruff `S` (bandit) rules enabled; `uv.lock` committed.
- **Reliability:** targets fail on any warning treated as error in CI (`--exit-non-zero-on-fix` not used; `ruff check` only).
- **Steps:** 1. `uv init` layout with `src/`. 2. Add dependencies with ranges. 3. Configure Ruff, Pyright, pytest (`asyncio_mode=auto`). 4. Wire Make targets. 5. Smoke test.
- **Failure cases:** Python 3.14 missing → uv installs it (`uv python install 3.14`) and the target says so.
- **Tests:** `test_smoke.py` imports `nuroli`.
- **Verify:** `make fmt-check lint typecheck test-unit`.
- **Acceptance:** all four pass; `uv.lock` present; Pyright strict globs correct.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** exact dependency versions locked, for NU-006 and later.
- **Reason:** tooling before code so every later ticket has the same gate.
- **Practices:** import-boundary lint (configured in NU-006).
- **Status:** merged

#### NU-003 Frontend toolchain: Vite, React 19, TypeScript, ESLint, Prettier, Vitest
- **Phase:** 1 · **Context:** platform
- **Objective:** `frontend/` scaffold with pnpm, Vite, React 19, strict TypeScript, React Router, TanStack Query, react-markdown, rehype-sanitize, ESLint (typescript-eslint, react-hooks, jsx-a11y), Prettier, Vitest with Testing Library, Playwright installed; Make targets for the frontend parts of `fmt`, `lint`, `typecheck`, `test-fe`.
- **Outcome:** `make test-fe` runs one passing test; `pnpm dev` serves a placeholder.
- **Dependencies:** NU-001 · **Prerequisites:** Node LTS, pnpm.
- **Files:** `frontend/**` (scaffold), `make/frontend.mk`.
- **Ownership:** serialized (`package.json`, `pnpm-lock.yaml`); `make/frontend.mk` is frontend-area owned.
- **Domain:** none · **Contracts:** `tsconfig` strict with `noUncheckedIndexedAccess`; Vite proxy `/api` to `http://localhost:8000` in dev.
- **Security:** `pnpm audit --audit-level=high` clean; no CDN scripts.
- **Reliability:** lockfile frozen in CI.
- **Steps:** scaffold, configure, add smoke test, wire targets.
- **Failure cases:** audit finding above high → stop and ask.
- **Tests:** `App.test.tsx` renders placeholder text.
- **Verify:** `make fmt-check lint typecheck test-fe`.
- **Acceptance:** all pass; `pnpm-lock.yaml` committed; jsx-a11y rules on.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** locked versions; proxy configuration for NU-010.
- **Reason:** same gate for frontend before any screen exists.
- **Practices:** WCAG (lint rules only at this stage).
- **Status:** merged

#### NU-004 Pre-commit, gitleaks, and the pull-request workflow skeleton
- **Phase:** 1 · **Context:** platform
- **Objective:** `.pre-commit-config.yaml` (Ruff, Prettier, ESLint, gitleaks, forbid `.env`, reject commit messages with `Co-Authored-By` or `Signed-off-by` trailers), `make audit` (pip-audit, pnpm audit, gitleaks), `make deps-update`, and workflows `backend.yml` (`backend-quality`, `backend-tests` unit only for now), `frontend.yml` (`frontend-quality`, `frontend-tests`), `audit.yml`, `conventions.yml` (branch regex, commit subject regex, author and committer name and email equal to the owner's values set in the workflow, no trailers).
- **Outcome:** Every pull request runs the gates that exist so far.
- **Dependencies:** NU-002, NU-003 · **Prerequisites:** GitHub repository with Actions.
- **Files:** `.pre-commit-config.yaml`, `.github/workflows/{backend,frontend,audit,conventions}.yml`, `make/backend.mk`, `make/frontend.mk`, `make/infra.mk` (`audit`, `setup`, `deps-update`).
- **Ownership:** serialized (`.github/`).
- **Domain:** none · **Contracts:** workflow `permissions: contents: read`; jobs named exactly as section 5.2; conventions regex `^ticket/NU-\d{3}-[a-z0-9-]+$` and `^(feat|fix|chore|docs|test|refactor)(\([a-z-]+\))?: NU-\d{3} .+`.
- **Security:** read-only token; pinned action versions by SHA; no secrets referenced.
- **Reliability:** jobs cache uv and pnpm stores; a failing job blocks merge.
- **Steps:** write pre-commit config; wire `make setup` to install hooks; write the four workflows; write `make deps-update`.
- **Failure cases:** gitleaks false positive → add a documented allowlist entry with reason, never disable.
- **Tests:** a deliberately mis-named branch and a commit with a co-author trailer each fail `conventions` (verified once in a throwaway PR and recorded in evidence).
- **Verify:** `make audit`; `pre-commit run --all-files`; a pull request with all jobs green.
- **Acceptance:** all jobs green on the pull request; hooks installed by `make setup`.
- **Done:** standard · **Reviewer evidence:** standard plus workflow permissions check.
- **Handoff:** job names for later tickets to extend (`migrations`, `e2e`).
- **Reason:** gates must exist before feature code, or evidence is only an agent's word.
- **Practices:** Conventional Commits and ticket branches.
- **Status:** merged

#### NU-005 OpenCode agent definitions and pull-request evidence template
- **Phase:** 1 · **Context:** platform
- **Objective:** `.opencode/agents/implementer.md` and `.opencode/agents/reviewer.md` with permissions from section 3.1 and prompts that point to AGENTS.md and this document's sections; `.github/pull_request_template.md` with the evidence headings from section 4.6 including the Preflight heading; `make worktree` and `make worktree-clean` writing and honouring `.worktree.env` (project name, port offsets, `BASE_COMMIT`, `BASE_SCHEMA_HEAD`; section 4.3).
- **Outcome:** An OpenCode session can be started as implementer or reviewer with the right permissions; every pull request starts with the evidence skeleton.
- **Dependencies:** NU-004 · **Prerequisites:** OpenCode installed locally (not in CI).
- **Files:** `.opencode/agents/*.md`, `.github/pull_request_template.md`, `make/agents.mk`, `Makefile` (include of `.worktree.env` when present).
- **Ownership:** serialized.
- **Domain:** none · **Contracts:** reviewer `permission.edit: deny`, `permission.write: deny`; no `model` field in committed agent files.
- **Security:** agents cannot read `.env` (prompt instruction plus `.gitignore`; note that OpenCode permission globs cannot block file reads by path in all versions — recorded as a limitation).
- **Reliability:** `make worktree` refuses to run with uncommitted changes or a name not matching the regex; port offsets are deterministic from the ticket number.
- **Steps:** write agent files; write template; write worktree target using `git worktree add -b`.
- **Failure cases:** existing worktree name → target fails with instructions.
- **Tests:** `make worktree T=NU-999` creates the worktree and `.worktree.env` with offset 999; `make worktree-clean T=NU-999` removes it; agent files parse (OpenCode `--print-config` if available, else YAML frontmatter lint).
- **Verify:** `make worktree T=NU-999 && cat ../nuroli-NU-999/.worktree.env && make worktree-clean T=NU-999`.
- **Acceptance:** both agents documented in AGENTS.md; template present; worktree round trip works.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** none.
- **Reason:** implementer and reviewer separation must be mechanical before feature tickets start.
- **Practices:** AGENTS.md entry file.
- **Status:** merged

#### NU-049 Graphify: graph targets, post-commit refresh, agent guidance
- **Phase:** 1 · **Context:** platform (agents area)
- **Objective:** `make/graph.mk` with `graph-build`, `graph-update`, `graph-watch` wrapping the `graphify` CLI (installed as a uv tool by `make setup`: `uv tool install graphifyy`); the pre-commit framework `post-commit` stage running `make graph-update`; `make worktree` extended to build the graph for a new worktree; AGENTS.md section describing when to run `graphify query`, `explain`, `path`, and `god-nodes`; `.gitignore` already covers `graphify-out/` (NU-001).
- **Outcome:** Every worktree has a current code graph after every commit without any LLM call, and agents know how to ask it questions.
- **Dependencies:** NU-004, NU-005 · **Prerequisites:** `uv` available; network for the one-time tool install.
- **Files:** `make/graph.mk`, `make/agents.mk` (worktree graph build), `.pre-commit-config.yaml` (post-commit stage only), `AGENTS.md` (graph section), `README.md` (developer section).
- **Ownership:** serialized (`AGENTS.md`, `.pre-commit-config.yaml`); agents area.
- **Domain:** none.
- **Contracts:** target names and behavior per section 2.1; graph scope is `.` with AST-only extraction (docs are ignored by `graphify update`); `graph-update` never passes `--force` unless `FORCE=1`.
- **Security:** graphify makes no network calls in this flow and reads no API keys; `graphify-out/` is ignored so no extracted source structure is committed; the hook runs only local commands.
- **Reliability:** the post-commit hook must never fail a commit: it runs with `always_run` and exits 0 after printing an error if the graph cannot be updated, and writes `graphify-out/.needs_rebuild` so the next `make preflight` runs `graph-build`.
- **Steps:** 1. `make setup` installs graphifyy as a uv tool and prints its version. 2. Write `make/graph.mk`. 3. Add the post-commit stage hook. 4. Extend `make worktree`. 5. Write the AGENTS.md section with the four rules from section 3.5 condensed to six lines. 6. Verify on the current repository (the graph will be small until code exists).
- **Failure cases:** graphify not installed → targets print the install command and exit 1; shrink refusal → message explains `FORCE=1`; graph build on an empty code tree → `graph-build` reports "no code files" and exits 0 so early Phase 1 commits are not blocked.
- **Tests:** shell tests: after a commit that adds a Python file, `graphify-out/graph.json` contains a node whose `source_file` is that file and `built_at_commit` equals `HEAD`; `make graph-update FORCE=1` after deleting the file removes the node; the hook exits 0 when `graphify-out/` is deleted first.
- **Verify:** `make graph-build && make graph-update && git commit --allow-empty -m "chore: NU-049 hook check" && test -f graphify-out/graph.json` (the empty commit is amended away before the pull request).
- **Acceptance:** targets work from a clean clone after `make setup`; hook runs after commit and never blocks it; AGENTS.md section present; `graphify god-nodes` prints on the current tree.
- **Done:** standard · **Reviewer evidence:** standard plus the hook log from a commit.
- **Handoff:** graph output paths for NU-050.
- **Reason:** R-41 requires the graph to be current at every commit before any agent relies on it; wiring it in Phase 1 means every later ticket is developed with the graph present.
- **Practices:** Graphify code graph; AGENTS.md entry file.
- **Status:** merged

### Phase 2 — Minimal project structure and domain boundaries

#### NU-006 Backend module layout, import boundaries, app factory, health endpoint
- **Phase:** 2 · **Context:** platform
- **Objective:** Packages `shared_kernel`, `ports`, `platform`, `adapters`, and `identity`, `conversations`, `knowledge` each with `domain`, `application`, `infrastructure`, `api` subpackages; an empty `api/router.py` per module; `import-linter` contracts from section 2.3 wired into `make lint`; `main.py` app factory including the three module routers and the platform routers once, with `/health`; uvicorn entry with one worker.
- **Outcome:** `uvicorn nuroli.main:app` serves `/health` → `{"status":"ok"}`; a forbidden import fails `make lint`.
- **Dependencies:** NU-002 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/**/__init__.py`, `backend/src/nuroli/main.py`, `backend/pyproject.toml` (import-linter section), `backend/tests/unit/test_boundaries.py`, `backend/tests/integration/test_health.py`.
- **Ownership:** backend platform; `pyproject.toml` serialized.
- **Domain:** none yet · **Contracts:** `/health` per ARCHITECTURE.md section 6.1; import contracts per section 2.3 of this document.
- **Security:** app factory installs the JSON error handler skeleton (internal errors return the envelope with `internal_error` and a request id; no stack traces).
- **Reliability:** `/health` does not touch the database.
- **Steps:** create packages and empty routers; write contracts; app factory including all routers; health router in `platform/health.py`; tests.
- **Failure cases:** a test that adds `from nuroli.identity.infrastructure import x` inside `conversations/domain` must fail lint (test uses a temp file and runs `lint-imports`).
- **Tests:** boundary violation detected; health returns 200 with the body.
- **Verify:** `make lint typecheck test-unit`; `uv run uvicorn nuroli.main:app & curl -s localhost:8000/health`.
- **Acceptance:** contracts enforce all five rules; health endpoint works; envelope handler present.
- **Done:** standard · **Reviewer evidence:** standard plus proof that a violating import fails.
- **Handoff:** package map for all later backend tickets; feature tickets add routes only inside their module's `api/router.py`.
- **Reason:** boundaries enforced by a tool from the first line keep DDD-lite honest with weak models, and a fixed router registration removes `main.py` as a conflict point.
- **Practices:** import-boundary lint; FastAPI structure rules.
- **Status:** merged

#### NU-007 Shared kernel: ids, Source value object, sanitizer, domain errors
- **Phase:** 2 · **Context:** shared kernel
- **Objective:** `shared_kernel/ids.py` (typed `NewType` ids and `new_id()` using `uuid.uuid7()`), `shared_kernel/source.py` (`Source` frozen dataclass, `sanitize_sources(raw: list[dict]) -> list[Source]` enforcing https, length limits, host-derived publisher, de-duplication), `shared_kernel/errors.py` (`DomainError`, `NotFound`, `InvalidState`, `ValidationFailed`, `StaleRevision`).
- **Outcome:** Value objects and errors every module uses exist with tests.
- **Dependencies:** NU-006 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/shared_kernel/*.py`, `backend/tests/unit/shared_kernel/*.py`.
- **Ownership:** serialized (shared kernel).
- **Domain:** `Source` value object; error hierarchy.
- **Contracts:** `Source` fields and limits per ARCHITECTURE.md section 4.3; error to HTTP mapping table per section 6 (implemented in NU-018, declared here as attributes `code`, `http_status`).
- **Security:** sanitizer rejects `javascript:`, `data:`, `http:`, private hosts are allowed here (search results) but must be https; snippet truncated at 500 characters; title at 300.
- **Reliability:** pure functions; no I/O.
- **Steps:** test-first: write tests for each rule, then implement.
- **Failure cases:** malformed URL, missing title (dropped), duplicate URL (first kept), 0 results.
- **Tests:** parametrized sanitizer tests; id monotonicity smoke; error attributes.
- **Verify:** `make lint typecheck test-unit`.
- **Acceptance:** every rule in Security has a test; 100 percent of sanitizer branches exercised (reviewer reads tests, no coverage gate).
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** exact `Source` shape for NU-023 and NU-029.
- **Reason:** sources cross two modules and the API; one definition prevents drift.
- **Practices:** test-first.
- **Status:** merged

#### NU-008 Frontend app shell: tokens, layout, router, providers, accessibility skeleton
- **Phase:** 2 · **Context:** frontend platform
- **Objective:** `styles/tokens.css` copied from DESIGN.html section 3; app layout (rail, context list slot, main column; mobile tab bar) per DESIGN.html section 4 and 15; React Router routes for every path in DESIGN.html section 4 rendering placeholders; TanStack Query provider; skip link, landmarks, focus-to-h1 on route change; Playwright configured with axe and a `make e2e` target that, until NU-022, starts the Vite dev server through Playwright's `webServer` option with no backend.
- **Outcome:** The shell renders at 1440px and 390px with correct landmarks and passes axe.
- **Dependencies:** NU-003 · **Prerequisites:** none.
- **Files:** `frontend/src/app/**`, `frontend/src/styles/**`, `frontend/src/components/{Layout,Rail,TabBar,SkipLink}.tsx`, `frontend/tests/e2e/shell.spec.ts`, `frontend/playwright.config.ts`, `make/frontend.mk` (`e2e`).
- **Ownership:** frontend platform.
- **Domain:** none · **Contracts:** route list; token names.
- **Security:** CSP-compatible (no inline scripts or styles injected at runtime).
- **Reliability:** layout has no horizontal scroll at 320px effective width.
- **Steps:** tokens; primitives (Button, Field, Pill, Alert, Empty) per DESIGN.html section 3 with unit tests; layout; router; e2e.
- **Failure cases:** unknown route → "Not found" screen with link home.
- **Tests:** Vitest for primitives (disabled state keeps focusability; alert roles); e2e: landmarks present, skip link works, axe clean at both widths.
- **Verify:** `make test-fe`; `make e2e` (shell spec).
- **Acceptance:** all routes render; axe clean; keyboard reaches every control.
- **Done:** standard · **Reviewer evidence:** standard plus screenshots at both widths attached.
- **Handoff:** component API of primitives for feature tickets.
- **Reason:** shared shell and primitives prevent each feature ticket from inventing its own layout.
- **Practices:** WCAG 2.2 AA with axe.
- **Status:** merged

#### NU-050 Graphify: impact, conflict, overlap reports, preflight, CI graph job
- **Phase:** 2 · **Context:** platform (agents area)
- **Objective:** `scripts/graph_impact.py` (changed files against a base ref → changed nodes, communities, affected nodes outside the changed files via reverse traversal depth 2, god nodes touched; Markdown report), `scripts/graph_conflicts.py` (branch mode: overlap of changed-plus-affected node sets with every other `origin/ticket/*` branch; planning mode `--paths-a/--paths-b`: community overlap between two ownership boundaries), Make targets `graph-impact`, `graph-conflicts`, `graph-overlap`, `preflight` (section 2.1 semantics including baseline comparison and `built_at_commit` check), and `.github/workflows/graph.yml`.
- **Outcome:** Implementers, reviewers, and the integrator see blast radius and overlap before every merge, and CI shows it on every pull request.
- **Dependencies:** NU-049, NU-006, NU-008 · **Prerequisites:** a code graph with at least the module skeletons.
- **Files:** `scripts/graph_impact.py`, `scripts/graph_conflicts.py`, `scripts/tests/test_graph_scripts.py`, `make/graph.mk`, `.github/workflows/graph.yml`, `.github/pull_request_template.md` (Preflight heading), `AGENTS.md` (preflight rule).
- **Ownership:** serialized (`.github/`, `AGENTS.md`); agents area.
- **Domain:** none.
- **Contracts:** scripts read only `graphify-out/graph.json` (fields `id`, `label`, `source_file`, `community`, `community_name`, `built_at_commit`) and git; they depend on no application code; report formats are fixed Markdown with the sections Baseline, Changed nodes, Affected nodes, Communities, God nodes, Conflicts; exit codes: 0 report written, 1 graph missing or unhealthy, 2 branch not rebased or baseline moved (preflight only).
- **Security:** workflow permissions `contents: read` only; reports contain file paths and symbol names, never file contents; no network access beyond git fetch.
- **Reliability:** scripts run under 10 seconds on the expected graph size; `preflight` refuses to run with a dirty tree so `built_at_commit` is meaningful; the CI job uploads the report even when the impact set is empty.
- **Steps:** 1. Write the scripts test-first against a fixture `graph.json` and a temporary git repository with two branches. 2. Wire targets. 3. Write `preflight` as a shell sequence in `make/graph.mk` calling the scripts. 4. Add the workflow with job summary output. 5. Update the PR template and AGENTS.md.
- **Failure cases:** no other ticket branches (empty conflicts section); node with no `source_file` (ignored, counted); base ref missing (exit 1 with message); graph built at a different commit (preflight rebuilds, then re-checks); two Alembic heads (preflight exit 2 naming both).
- **Tests:** unit tests for both scripts on fixtures (changed-file mapping, reverse traversal depth, overlap intersection, planning mode); a shell test for `preflight` exit codes on a rebased branch, a stale branch, and a dirty tree.
- **Verify:** `make graph-impact BASE=origin/rebuild/v1`; `make graph-overlap A=backend/src/nuroli/identity B=frontend/src/features/auth`; `make preflight`; workflow green on the pull request with the summary visible.
- **Acceptance:** reports produced with the fixed sections; preflight exit codes verified; CI job green and non-blocking on impact content.
- **Done:** standard · **Reviewer evidence:** standard plus the reviewer's own preflight output on the branch.
- **Handoff:** from this ticket on, every pull request carries a Preflight section and every lane pair requires `make graph-overlap` (section 4.9).
- **Reason:** turns the four Graphify rules in section 3.5 into commands with exit codes, so the coordinator, implementer, and reviewer act on the same report instead of on impressions.
- **Practices:** Graphify code graph; test-first (scripts have logic).
- **Status:** merged

### Phase 3 — Configuration and secret boundaries

#### NU-009 Settings, fail-fast validation, logging, request ids
- **Phase:** 3 · **Context:** platform
- **Objective:** `platform/settings.py` (pydantic-settings, `NUROLI_` prefix, every variable in ARCHITECTURE.md section 16 with types, defaults, and validators: URL shape, secret length ≥ 32, limits > 0), `platform/logging.py` (JSON or text, redaction of keys, tokens, emails beyond the first two characters), request-id middleware adding `X-Request-Id` and including it in the error envelope.
- **Outcome:** Misconfiguration stops startup with a readable list; every log line is structured; every error response carries a request id.
- **Dependencies:** NU-006 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/platform/{settings,logging,middleware}.py`, `backend/src/nuroli/main.py`, `backend/tests/unit/platform/*`, `.env.example` (comments only).
- **Ownership:** backend platform.
- **Domain:** none · **Contracts:** variable names and defaults per ARCHITECTURE.md sections 11.1, 16, and R-21; `X-Request-Id` header.
- **Security:** settings `repr` and logs never include secret fields (Pydantic `SecretStr`); startup log prints model host and model name only.
- **Reliability:** startup validation collects all errors before exiting.
- **Steps:** test-first for validators and redaction; implement; wire into app factory.
- **Failure cases:** missing required variable; invalid URL; `NUROLI_SEARCH_PROVIDER=tavily` without key → error naming both variables.
- **Tests:** unit tests for each validator and the redaction filter; integration test that `/health` error path includes request id.
- **Verify:** `make test-unit test-integration`; `NUROLI_MODEL_BASE_URL= uv run python -m nuroli.main` exits non-zero listing the missing variable.
- **Acceptance:** all variables typed; secrets redacted in a captured log; request id present on an error response.
- **Done:** standard · **Reviewer evidence:** standard plus a captured log sample showing redaction.
- **Handoff:** `Settings` field names for every later ticket.
- **Reason:** configuration is the secret boundary; it must be strict before credentials exist anywhere.
- **Practices:** OWASP ASVS (configuration and logging items).
- **Status:** merged

#### NU-010 Compose stacks, Dockerfiles, nginx, fake-model placeholder, `make dev`
- **Phase:** 3 · **Context:** platform / infra
- **Objective:** `compose.yaml` (web, api, db per ARCHITECTURE.md section 15), `compose.dev.yaml` (bind mounts, reload, Vite dev server, exposed db port, fake-model service placeholder), `infra/docker/api.Dockerfile` (multi-stage, uv, non-root, Python 3.14, single uvicorn worker), `infra/docker/web.Dockerfile` (pnpm build, nginx), `infra/nginx/nginx.conf` (static caching, `/api` proxy with buffering off, 64k body limit, security headers, CSP), Make targets `dev`, `up`, `down`. All published ports and the project name come from the variables in section 4.3, so worktrees do not collide.
- **Outcome:** `make dev` starts db, api (health ok), and the frontend dev server; `make up` starts the release-shaped stack from local builds.
- **Dependencies:** NU-008, NU-009 · **Prerequisites:** Docker with Compose v2.
- **Files:** `compose.yaml`, `compose.dev.yaml`, `infra/**`, `make/infra.mk`.
- **Ownership:** serialized (infra, compose).
- **Domain:** none · **Contracts:** service names, ports, volume name, `extra_hosts`, headers per ARCHITECTURE.md sections 15 and 17.
- **Security:** only `web` publishes a port in `compose.yaml`; containers run as non-root; `.env` mounted only as `env_file` for `api` and `db`; no secrets in images (verified by `docker history`).
- **Reliability:** `db` healthcheck; `api` `depends_on` healthy; restart policies `unless-stopped` in release.
- **Steps:** Dockerfiles; nginx config; compose files; targets; smoke.
- **Failure cases:** port in use → clear error from Compose; missing `.env` → `make up` fails with "copy .env.example to .env".
- **Tests:** shell smoke: `make up` then `curl web/health` returns ok through nginx; `docker compose config` valid; header check with `curl -I`; two stacks with different `.worktree.env` files run at once.
- **Verify:** `docker compose -f compose.yaml config`; `make up && curl -s localhost:8080/health && make down`.
- **Acceptance:** both stacks start; headers present; only web port published; images contain no `.env`.
- **Done:** standard · **Reviewer evidence:** standard plus `docker compose ps` and `curl -I` outputs.
- **Handoff:** service names and internal URLs for NU-011 and NU-022.
- **Reason:** the deployment shape must exist early so every later slice is tested in it.
- **Practices:** reliability checks (section 5.7).
- **Status:** merged

### Phase 4 — Database connection and migration foundation

#### NU-011 Async engine, unit of work, Alembic, migration-on-start, readiness, integration harness
- **Phase:** 4 · **Context:** platform
- **Objective:** `platform/db.py` (engine from settings, `UnitOfWork`, FastAPI dependency), `platform/wiring.py` skeleton (composition root), `platform/lifespan.py` (startup and shutdown hooks; timers are added by later tickets), Alembic configured for async with `citext` extension in the first migration, `nuroli migrate` command run by the api container entrypoint under advisory lock `pg_advisory_lock(7245)`, `/ready` checking connectivity and `alembic current == head`, `make migrate`, `make migration`, `make migrate-check`, integration test fixtures (per-test transaction rollback), CI `migrations` job and PostgreSQL service in `backend-tests`.
- **Outcome:** The API starts only after migrations apply; tests run against a real database in CI.
- **Dependencies:** NU-009, NU-010 · **Prerequisites:** dev stack.
- **Files:** `backend/src/nuroli/platform/{db,wiring,lifespan,cli}.py`, `backend/alembic.ini`, `backend/migrations/**`, `backend/tests/conftest.py`, `backend/tests/integration/test_ready.py`, `infra/docker/api-entrypoint.sh`, `.github/workflows/backend.yml`, `make/backend.mk`.
- **Ownership:** serialized (migrations, `.github`, infra).
- **Domain:** none · **Contracts:** `/ready` per ARCHITECTURE.md section 6.1; `UnitOfWork` interface per section 2.3 of this document.
- **Security:** database URL never logged; migrations run with the application role (no superuser) except `CREATE EXTENSION citext`, which the first migration performs and which requires the role to own the database (documented in README).
- **Reliability:** two API containers starting together do not race (advisory lock test with two processes); `/ready` returns 503 with `database: "unavailable"` when the database is down.
- **Steps:** engine and uow; Alembic env; migration 0001 (extension only); entrypoint; readiness; fixtures; CI.
- **Failure cases:** head mismatch → `/ready` 503 `migrations: "pending"`; downgrade of 0001 removes the extension.
- **Tests:** integration: ready ok; ready 503 when database stopped (simulated by wrong URL fixture); migrate-check round trip; unit: uow commit and rollback semantics with a fake session.
- **Verify:** `make migrate migrate-check test-integration`; `make up` then `curl localhost:8080/ready`.
- **Acceptance:** all pass; CI `migrations` job green; entrypoint locks.
- **Done:** standard · **Reviewer evidence:** standard plus log excerpt of the lock acquisition.
- **Handoff:** fixture names (`db_session`, `client`) for every later backend ticket.
- **Reason:** authentication (next phase) needs tables, and migrations need to be safe before the first table exists.
- **Practices:** PostgreSQL migration rules.
- **Status:** merged

### Phase 5 — Login and registration

#### NU-012 Identity domain: User aggregate, Email, password and registration policies
- **Phase:** 5 · **Context:** identity
- **Objective:** `identity/domain/`: `User` aggregate with `register_with_password`, `register_with_google`, `verify_password` (via hasher port), `change_password`, `deactivate`; `Email` value object; `PasswordPolicy` (R-34); `RegistrationPolicy` (R-14); domain errors `EmailTaken`, `WeakPassword`, `RegistrationClosed`, `WrongCredentialType`.
- **Outcome:** Every identity rule exists as testable code with no framework.
- **Dependencies:** NU-007 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/identity/domain/**`, `backend/tests/unit/identity/**`.
- **Ownership:** identity.
- **Domain:** User aggregate, Email VO, policies; invariants per ARCHITECTURE.md section 4.3.
- **Contracts:** `PasswordHasherPort` protocol declared in `identity/application/ports.py`.
- **Security:** password never stored on the aggregate in plain form; hashing through the port only; the aggregate refuses a second credential type.
- **Reliability:** pure code.
- **Steps:** test-first for each invariant; implement.
- **Failure cases:** password 11 chars; 129 chars; email with uppercase normalizes; Google registration with unverified email rejected by the policy.
- **Tests:** one test per invariant and policy branch.
- **Verify:** `make test-unit`.
- **Acceptance:** all invariants in ARCHITECTURE.md section 4.3 (User) have a failing-then-passing test.
- **Done:** standard · **Reviewer evidence:** standard plus mapping of invariants to test names.
- **Handoff:** aggregate method signatures for NU-014 and NU-015.
- **Reason:** identity rules are the highest-risk logic; they are written and tested before any HTTP.
- **Practices:** test-first; OWASP password storage sheet.
- **Status:** not started

#### NU-013 Users and sessions tables, repositories, mappers
- **Phase:** 5 · **Context:** identity
- **Objective:** Migration 0002 `users` and `sessions` per ARCHITECTURE.md section 10; SQLAlchemy models; `UserRepository` and `SessionRepository` implementations and mappers; in-memory fakes in `tests/unit/identity/fakes.py`.
- **Outcome:** Users and sessions persist and load through repositories with ownership-free semantics (identity has no owner).
- **Dependencies:** NU-011, NU-012 · **Prerequisites:** dev stack.
- **Files:** `backend/migrations/versions/0002_*.py`, `backend/src/nuroli/identity/infrastructure/**`, `backend/tests/integration/identity/test_repositories.py`, `backend/tests/unit/identity/fakes.py`.
- **Ownership:** identity; migrations serialized.
- **Domain:** mapping only.
- **Contracts:** repository protocols per ARCHITECTURE.md section 4.6; check constraint on credential exclusivity; `citext` email.
- **Security:** `token_hash` stored, never the token; unique index on hash.
- **Reliability:** `purge_expired` deletes in one statement; migration downgrade works.
- **Steps:** migration; models; mappers; repositories; fakes; tests.
- **Failure cases:** duplicate email raises a mapped `EmailTaken`; both credentials set rejected by the database.
- **Tests:** integration round trips; constraint tests; fakes behave like the real ones (shared test module run against both).
- **Verify:** `make migrate-check test-integration test-unit`.
- **Acceptance:** shared repository tests pass for fake and real implementations.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** fake repository classes for use-case tests.
- **Reason:** persistence for identity before use cases keeps NU-014 focused on behavior.
- **Practices:** PostgreSQL migration rules.
- **Status:** not started

#### NU-014 Register, login, logout, me, options; Argon2 hasher; session cookie
- **Phase:** 5 · **Context:** identity
- **Objective:** Use cases `RegisterUser`, `LoginWithPassword`, `Logout`, `GetCurrentUser`; `Argon2PasswordHasher` adapter; session issuance (`platform/security.py`: token generation, hashing, cookie attributes from settings); routers for `/auth/options`, `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`; first-user-admin; registration flag.
- **Outcome:** A user can register, sign in, see themselves, and sign out with curl.
- **Dependencies:** NU-013 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/identity/{application,api}/**` (routes go in `api/router.py`), `backend/src/nuroli/adapters/argon2_hasher.py`, `backend/src/nuroli/platform/{security,wiring}.py`, `backend/tests/{unit,integration}/identity/**`.
- **Ownership:** identity; `api/schemas.py` serialized.
- **Domain:** use cases per ARCHITECTURE.md section 4.8.
- **Contracts:** endpoints, bodies, codes per ARCHITECTURE.md section 6.1; cookie per R-13; error envelope.
- **Security:** Argon2id parameters at or above OWASP minimums and asserted by a test; constant-time verification; login failure returns the same error for unknown email and wrong password; cookie `HttpOnly; Secure; SameSite=Lax; Path=/`; registration closed returns 403 without creating anything.
- **Reliability:** duplicate registration race handled by the unique constraint, mapped to 409.
- **Steps:** hasher with test; use cases test-first with fakes; security helpers; routers; integration tests.
- **Failure cases:** all codes in section 6.1 for these endpoints; inactive user login; second user is `member`.
- **Tests:** unit for use cases; integration for each endpoint and code; security-tagged test that the cookie has all attributes and that `/auth/me` without cookie is 401.
- **Verify:** `make test-unit test-integration`; curl script in evidence: register, me, logout, me (401).
- **Acceptance:** all endpoint rows verified; first user admin; flag respected.
- **Done:** standard · **Reviewer evidence:** standard plus Argon2 parameter assertion output.
- **Handoff:** `issue_session` and `current_user` helper locations for NU-015 and NU-018.
- **Reason:** authentication must exist before any owned resource so ownership tests are possible from the first feature.
- **Practices:** OWASP ASVS authentication and session items.
- **Status:** not started

#### NU-015 Google sign-in with PKCE, state cookie, and one-method-per-email
- **Phase:** 5 · **Context:** identity
- **Objective:** `GoogleOAuthAdapter` (Authlib) implementing `GoogleOAuthPort`; use cases `StartGoogleSignIn`, `CompleteGoogleSignIn`; routes `/auth/google/start` and `/auth/google/callback`; signed state cookie (10 minutes) carrying state and PKCE verifier; R-16 rules; `google_enabled` in `/auth/options`.
- **Outcome:** A user can sign in with Google when configured; conflicts produce the documented redirects.
- **Dependencies:** NU-014 · **Prerequisites:** Google client id and secret for manual verification only (not in CI).
- **Files:** `backend/src/nuroli/adapters/google_oauth.py`, `backend/src/nuroli/identity/{application,api}/**` (new files and the router), `backend/tests/contract/test_google_oauth.py`, `backend/tests/integration/identity/test_google.py`, `backend/tests/contract/fixtures/google/*.json`.
- **Ownership:** identity.
- **Domain:** `register_with_google`, credential exclusivity.
- **Contracts:** redirects and error codes per ARCHITECTURE.md section 6.1 and 8; redirect URI `${NUROLI_PUBLIC_ORIGIN}/api/v1/auth/google/callback`.
- **Security:** state compared in constant time; PKCE S256; ID token signature, issuer, audience, expiry verified through Authlib against Google's JWKS (fixture in contract tests); `email_verified` required; no auto-link; state cookie deleted after use; callback rejects reuse.
- **Reliability:** Google unreachable → redirect with `error=google_unavailable`, nothing created.
- **Steps:** adapter with contract tests against recorded token and JWKS responses; use cases test-first; routes; integration tests with a fake port.
- **Failure cases:** state mismatch; expired cookie; unverified email; email used by password; registration closed for a new Google user; known subject with changed email (subject wins, email not updated in v1).
- **Tests:** contract (respx), unit (use cases), integration (redirect codes), security-tagged (state mismatch, reuse).
- **Verify:** `make test-contract test-unit test-integration`; manual sign-in against a real Google client recorded in evidence with screenshots.
- **Acceptance:** every failure case has a test; manual sign-in works once.
- **Done:** standard · **Reviewer evidence:** standard plus the manual verification note.
- **Handoff:** none.
- **Reason:** Google is a required login method and its validation rules are the most error-prone part of auth.
- **Practices:** OWASP ASVS OAuth items; adapter contract tests.
- **Status:** not started

#### NU-016 Frontend authentication screens and session handling
- **Phase:** 5 · **Context:** frontend auth
- **Objective:** `/login` and `/register` per DESIGN.html section 6; `features/auth` api and hooks (`useMe`, `useLogin`, `useRegister`, `useLogout`); auth guard redirecting to `/login`; Google button when enabled; all error cases from DESIGN.html section 6 including the callback `error` query; session-expired banner on 401 with local state preserved; `frontend/src/api/client.ts` with the CSRF header and envelope parsing.
- **Outcome:** A user can register, sign in with either method, and sign out in the browser.
- **Dependencies:** NU-008, NU-014 (NU-015 is not required: the Google button is a link shown when `/auth/options` reports it enabled, and the callback error codes are strings from ARCHITECTURE.md section 6.1) · **Prerequisites:** dev stack.
- **Files:** `frontend/src/features/auth/**` (including `types.ts`), `frontend/src/api/{client,errors}.ts`, `frontend/src/app/guards.tsx`, `frontend/tests/e2e/auth.spec.ts`.
- **Ownership:** frontend auth; `frontend/src/api/` serialized.
- **Domain:** none.
- **Contracts:** endpoints per ARCHITECTURE.md section 6.1; header `X-Requested-With: nuroli` on every non-GET; error envelope type.
- **Security:** no token handling in JavaScript; password field `autocomplete` attributes; errors shown verbatim from the envelope only; Google button is a plain link to the start endpoint.
- **Reliability:** network failure shows a retryable alert; busy buttons prevent double submit.
- **Steps:** client; hooks with MSW tests; screens with primitives; guard; e2e.
- **Failure cases:** every row in DESIGN.html section 6 table.
- **Tests:** Vitest with MSW for hooks and error rendering; e2e: register, sign out, sign in, wrong password, closed registration (stack started with the flag false), axe on both screens, keyboard-only flow.
- **Verify:** `make test-fe e2e`.
- **Acceptance:** e2e journeys pass; axe clean; focus moves to the first invalid field on submit.
- **Done:** standard · **Reviewer evidence:** standard plus screenshots.
- **Handoff:** `apiClient` usage pattern for all feature tickets.
- **Reason:** login in the browser is the first vertical slice and proves the shell, client, and API together.
- **Practices:** WCAG with axe; adapter contract tests (MSW).
- **Status:** not started

#### NU-017 Operator commands: reset-password, delete-user
- **Phase:** 5 · **Context:** identity / platform
- **Objective:** `nuroli reset-password <email>` (temporary 20-character password printed once, `must_change_password` set, sessions revoked) and `nuroli delete-user <email>` (confirmation prompt, cascade) as argparse commands in `platform/cli.py` calling identity use cases `ResetPasswordByOperator` and `DeleteUser`.
- **Outcome:** Recovery and deletion work without email.
- **Dependencies:** NU-014 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/platform/cli.py`, `backend/src/nuroli/identity/application/operator.py`, `backend/tests/integration/identity/test_operator.py`, `README.md` (operations section).
- **Ownership:** identity; README serialized.
- **Domain:** use cases; `must_change_password` flag on User.
- **Contracts:** command names per DESIGN.html section 5.
- **Security:** commands run only inside the container (no HTTP); temporary password printed to stdout once, not logged; deletion requires typing the email.
- **Reliability:** unknown email exits 1 with a message.
- **Steps:** use cases test-first; commands; README section.
- **Failure cases:** unknown email; Google-only account reset (refused with explanation).
- **Tests:** integration tests invoking the commands with the CLI runner.
- **Verify:** `make test-integration`; `docker compose exec api nuroli reset-password user@example.org`.
- **Acceptance:** both commands documented and tested; sessions revoked after reset.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** `must_change_password` enforcement is completed in NU-019.
- **Reason:** R-15 makes the operator the recovery path; it must exist before users can lock themselves out.
- **Practices:** OWASP ASVS credential recovery items.
- **Status:** not started

### Phase 6 — Session, authorization, and ownership enforcement

#### NU-018 current_user dependency, CSRF, throttling, sliding sessions, error mapping, ownership test kit
- **Phase:** 6 · **Context:** platform / identity
- **Objective:** `current_user` dependency (session lookup, sliding expiry touch at most every 5 minutes, absolute expiry, revoked check); CSRF middleware (Origin equals `NUROLI_PUBLIC_ORIGIN` and header present on POST, PATCH, DELETE; exempt only the Google callback GET); login throttling (R-36) in `platform/ratelimit.py` with an in-memory store and a `Retry-After` header; full domain-error to HTTP mapping; hourly purge of expired sessions as an in-process timer in `platform/lifespan.py`; a reusable test kit `tests/integration/ownership.py` providing two users and an `assert_not_found_for_other_user(method, path)` helper.
- **Outcome:** Every protected endpoint shares one enforcement path; later tickets prove ownership with one helper call.
- **Dependencies:** NU-014 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/platform/{security,ratelimit,middleware,errors,lifespan}.py`, `backend/src/nuroli/identity/api/dependencies.py`, `backend/tests/integration/{ownership.py,test_csrf.py,test_throttle.py,test_sessions.py}`.
- **Ownership:** backend platform and identity.
- **Domain:** none new.
- **Contracts:** codes `csrf_rejected`, `rate_limited`, `unauthenticated`; session lifetimes R-35; throttle R-36.
- **Security:** Origin check is strict string equality after normalization; missing Origin on state-changing requests is rejected; throttle keys use normalized email and the client address from `X-Forwarded-For` only when the peer is the `web` container network (settings `NUROLI_TRUSTED_PROXY_CIDR`, default the Compose network); session lookup is by hash; revoked sessions are rejected even if unexpired.
- **Reliability:** the in-memory throttle and slot stores are documented as single-process; a startup log states it.
- **Steps:** test-first for each rule; implement; register middleware; kit.
- **Failure cases:** wrong Origin; missing header; expired session; revoked session; 11th failed login; `X-Forwarded-For` spoof from an untrusted peer ignored.
- **Tests:** security-tagged integration tests for each failure case; unit tests for the throttle window arithmetic.
- **Verify:** `make test-unit test-integration`.
- **Acceptance:** every rule has a test; kit used by a sample test against `/auth/me` structure (will be used by all owned resources).
- **Done:** standard · **Reviewer evidence:** standard plus explicit statement that the admin role is not checked anywhere (test `test_admin_role_grants_nothing`).
- **Handoff:** kit helper signature for NU-025, NU-034, NU-037.
- **Reason:** ownership isolation is the core security promise; centralizing it before resources exist makes every later ticket's ownership test a one-liner.
- **Practices:** OWASP ASVS session and access-control items; test-first.
- **Status:** not started

#### NU-019 Change password, forced change after reset, Account screen
- **Phase:** 6 · **Context:** identity / frontend auth
- **Objective:** Use case `ChangePassword` (verify current, policy, revoke other sessions, clear `must_change_password`); endpoint `POST /auth/password`; middleware that returns `password_change_required` (403) for every endpoint except password change, me, and logout when the flag is set; `/account` screen with display-name edit (`PATCH /auth/me` with `display_name`), change password, sign out; forced-change screen after temporary password sign-in.
- **Outcome:** Users manage their password; operator resets complete safely.
- **Dependencies:** NU-017, NU-018, NU-016 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/identity/**` (new use case, router additions), `frontend/src/features/auth/AccountScreen.tsx`, `frontend/src/features/auth/ForcePasswordChange.tsx`, tests.
- **Ownership:** identity; frontend auth.
- **Domain:** `change_password`, `must_change_password`.
- **Contracts:** endpoints `POST /auth/password` and `PATCH /auth/me` and code `password_change_required` per ARCHITECTURE.md section 6.1.
- **Security:** current password required; other sessions revoked; Google-only accounts get 409 `email_uses_google` on password change.
- **Reliability:** none special.
- **Steps:** use case test-first; endpoint; middleware; screens; e2e.
- **Failure cases:** wrong current password; weak new password; Google-only account.
- **Tests:** unit, integration, e2e (reset via CLI in the test stack, sign in, forced change, then normal access).
- **Verify:** `make test-unit test-integration e2e`.
- **Acceptance:** forced change blocks other routes; other sessions revoked (tested with two clients).
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** none.
- **Reason:** completes the recovery loop started in NU-017 and gives users control of their credential.
- **Practices:** OWASP ASVS.
- **Status:** not started

### Phase 7 — First simple model connection

#### NU-020 ChatModelPort, request and event types, FakeChatModel
- **Phase:** 7 · **Context:** ports / adapters
- **Objective:** `nuroli/ports/chat_model.py`: `ChatMessage`, `ChatRequest` (messages, max_tokens, temperature), `ChatEvent` union (`Delta`, `Done(usage, finish_reason)`, `Failure(code, message, retryable)`), `ChatCompletion`, `ChatModelPort`; `adapters/fakes.py`: `FakeChatModel` scripted by a list of events, with optional delays and a `calls` record for assertions.
- **Outcome:** Use cases can be written and tested before any real adapter exists.
- **Dependencies:** NU-007 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/ports/chat_model.py`, `backend/src/nuroli/adapters/fakes.py`, `backend/tests/unit/adapters/test_fakes.py`.
- **Ownership:** serialized (`ports/`).
- **Domain:** none.
- **Contracts:** port per ARCHITECTURE.md section 4.5; error codes per section 11.2.
- **Security:** none.
- **Reliability:** fake supports a "hang until cancelled" script for timeout tests.
- **Steps:** types; fake; tests.
- **Failure cases:** n/a.
- **Tests:** fake yields scripted events in order; records requests.
- **Verify:** `make lint typecheck test-unit`.
- **Acceptance:** port and fake documented in docstrings; Pyright strict passes.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** exact event types for NU-021 and NU-026.
- **Reason:** the port is the boundary that keeps provider details out of the domain; defining it first makes the adapter a pure implementation ticket.
- **Practices:** adapter contract tests (prepared).
- **Status:** not started

#### NU-021 OpenAI-compatible streaming adapter, error mapping, check-model, capabilities endpoint
- **Phase:** 7 · **Context:** adapters / platform
- **Objective:** `adapters/openai_compatible.py` implementing `ChatModelPort` per ARCHITECTURE.md section 11.2 (httpx async client, SSE parsing, timeouts from settings, one pre-first-byte retry, error mapping, usage extraction, `finish_reason`); `nuroli check-model` command; `GET /system/capabilities`; adapter factory in `platform/providers.py` choosing fake or real by settings (`NUROLI_MODEL_BASE_URL` pointing at the fake container is the dev default).
- **Outcome:** The configured model answers a one-token request from the container; misconfiguration is diagnosable.
- **Dependencies:** NU-020, NU-018 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/adapters/openai_compatible.py`, `backend/src/nuroli/platform/{providers,cli,system,wiring}.py`, `backend/tests/contract/test_openai_compatible.py`, `backend/tests/contract/fixtures/openai/*.txt`, `backend/tests/integration/test_capabilities.py`, `make/infra.mk` (`check-model`).
- **Ownership:** adapters and platform.
- **Domain:** none.
- **Contracts:** request and response shapes per section 11.2; capabilities per section 6.1.
- **Security:** `Authorization` header only when a key is set; key never logged or included in exceptions (test asserts `repr` of errors); extra headers from settings only; TLS verification on; private base URLs allowed (trusted config).
- **Reliability:** first-token timeout separate from total; retry once only before first byte; malformed chunks skipped with a warning and counted; connection closed mid-stream → `Failure(model_error, retryable=True)`.
- **Steps:** contract tests from recorded fixtures (success stream, `length`, 401, 404, 429, 500, malformed chunk, timeout); implement; factory; command; endpoint.
- **Failure cases:** all mapped codes per section 11.2.
- **Tests:** contract (respx); unit for SSE line parser; integration for capabilities (auth required, fields present, no base URL leaked).
- **Verify:** `make test-contract test-unit test-integration`; `make check-model` against the fake container.
- **Acceptance:** every mapping row tested; `check-model` prints outcome and never the key; capabilities returns model name and research flag.
- **Done:** standard · **Reviewer evidence:** standard plus fixture list.
- **Handoff:** factory function name for NU-026 and NU-034.
- **Reason:** the single model connection is the product's engine; it must be proven against recorded provider behavior before conversations use it.
- **Practices:** adapter contract tests; OWASP ASVS (secret handling).
- **Status:** not started

#### NU-022 Fake model container for development and end-to-end tests
- **Phase:** 7 · **Context:** infra
- **Objective:** `infra/fake-model/`: a small FastAPI app implementing `POST /v1/chat/completions` (streaming and non-streaming) with deterministic answers derived from the last user message, special trigger phrases for failure modes (`[[timeout]]`, `[[error500]]`, `[[length]]`), `usage` in responses, and a Tavily-shaped `POST /search` returning fixed sanitizable results (with trigger phrases `[[search-empty]]`, `[[search-error]]`); Dockerfile; service in `compose.dev.yaml` and a `compose.test.yaml` used by `make e2e`, which from this ticket on runs Playwright against the test stack (replacing the NU-008 dev-server mode).
- **Outcome:** Development and CI have a model with no key and no cost.
- **Dependencies:** NU-010 · **Prerequisites:** none.
- **Files:** `infra/fake-model/**`, `compose.dev.yaml`, `compose.test.yaml`, `make/frontend.mk` (`e2e`), `.github/workflows/e2e.yml`.
- **Ownership:** serialized (infra, compose, Makefile, `.github`).
- **Domain:** none.
- **Contracts:** OpenAI-compatible protocol subset used by NU-021; Tavily response shape used by NU-029; trigger phrases documented in the fake's README; the test stack sets `NUROLI_TAVILY_BASE_URL` to the fake container.
- **Security:** never published to a registry as part of the product; listens only on the Compose network.
- **Reliability:** streams with configurable delay so stop and timeout tests are deterministic.
- **Steps:** app; Dockerfile; compose; `make e2e` bringing the test stack up, running Playwright, tearing down; CI job.
- **Failure cases:** n/a.
- **Tests:** the fake's own tests (pytest, in `infra/fake-model/tests`); NU-021 contract tests run against it once as a sanity check.
- **Verify:** `make e2e` (runs NU-008 and NU-016 specs against the stack).
- **Acceptance:** e2e job green in CI using the fake model.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** trigger phrases for NU-026, NU-028, NU-031, NU-035 tests.
- **Reason:** I-07: every automated test must run without paid calls, so the model side of the stack must be fake and faithful.
- **Practices:** reliability checks.
- **Status:** not started

### Phase 8 — Conversations and streaming

#### NU-023 Conversation domain: aggregate, messages, invariants, ContextAssembler
- **Phase:** 8 · **Context:** conversations
- **Objective:** `conversations/domain/`: `Conversation` aggregate (`create(owner, first_message)` deriving the title per R-30, `add_user_message`, `start_reply(model_name, replies_to)`, `append_delta`, `complete(usage, finish_reason)`, `stop()`, `fail(code)`, `attach_sources`, `rename`), `Message` entity, `MessageState` enum, invariants from ARCHITECTURE.md section 4.3; `ContextAssembler` and `ResearchQueryPrompt` domain services with the system prompt text in `prompts.py`.
- **Outcome:** Every conversation rule is testable without a database or model.
- **Dependencies:** NU-007, NU-020 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/conversations/domain/**`, `backend/tests/unit/conversations/**`.
- **Ownership:** conversations.
- **Domain:** Conversation, Message, Source usage, ContextAssembler.
- **Contracts:** context budget behavior per R-21 and section 4.4; stopped marker text `[reply stopped by user]`; failed messages excluded.
- **Security:** system prompt states that user text, transcripts, and web snippets are data; the untrusted research block format is defined here and tested to contain no snippet outside the delimiters.
- **Reliability:** pure code.
- **Steps:** test-first per invariant and per assembler rule; implement.
- **Failure cases:** second streaming reply; sources on a user message; append after complete; content length limits; title from a 500-character message truncates at 80 with an ellipsis; budget dropping the oldest whole messages first but always keeping the latest user message.
- **Tests:** one per invariant; assembler tests with budgets; prompt snapshot tests (approved text committed).
- **Verify:** `make test-unit`.
- **Acceptance:** invariants in ARCHITECTURE.md section 4.3 (Conversation) all have tests; assembler never exceeds the budget in property-style tests over random message sizes.
- **Done:** standard · **Reviewer evidence:** standard plus invariant-to-test mapping.
- **Handoff:** method signatures for NU-026.
- **Reason:** the conversation rules and the prompt boundary are the heart of the product and must not be entangled with streaming plumbing.
- **Practices:** test-first; OWASP LLM prompt-injection sheet.
- **Status:** not started

#### NU-024 Conversations and messages tables, repository, mappers
- **Phase:** 8 · **Context:** conversations
- **Objective:** Migration 0003 `conversations` and `messages` per ARCHITECTURE.md section 10; models; `ConversationRepository` with `add`, `get_owned`, `list_owned` (cursor on `updated_at desc, id desc`), `save` (inserts new messages, updates changed assistant messages), `delete`; mapper; in-memory fake.
- **Outcome:** Conversations persist with owner-scoped access.
- **Dependencies:** NU-011, NU-023 · **Prerequisites:** dev stack.
- **Files:** `backend/migrations/versions/0003_*.py`, `backend/src/nuroli/conversations/infrastructure/**`, `backend/tests/integration/conversations/test_repository.py`, `backend/tests/unit/conversations/fakes.py`.
- **Ownership:** conversations; migrations serialized.
- **Domain:** mapping only.
- **Contracts:** repository protocol per section 4.6; cursor format `base64(updated_at|id)`; `summary_state` column joined later (NU-033 adds the join).
- **Security:** every query filters by `owner_id`; tested with two users.
- **Reliability:** `save` is idempotent for unchanged messages; unique `(conversation_id, sequence)` prevents duplicate appends.
- **Steps:** migration; models; mappers; repository; fake; shared repository test suite.
- **Failure cases:** foreign owner returns None; cursor tampering returns 422 at the API (mapping added in NU-025).
- **Tests:** shared suite for fake and real; ownership tests; cursor pagination order and stability.
- **Verify:** `make migrate-check test-integration test-unit`.
- **Acceptance:** shared suite passes for both implementations.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** cursor helper for NU-033 list endpoints.
- **Reason:** persistence separated from behavior keeps the streaming ticket small.
- **Practices:** PostgreSQL rules.
- **Status:** not started

#### NU-025 Conversation CRUD use cases and endpoints
- **Phase:** 8 · **Context:** conversations
- **Objective:** Use cases `CreateConversation`, `ListConversations`, `GetConversation`, `RenameConversation`, `DeleteConversation`; routers for the five non-streaming endpoints in ARCHITECTURE.md section 6.2; message response schema including `superseded` computation (a failed reply followed by a later reply to the same user message); R-37 stale-streaming presentation on read.
- **Outcome:** Conversations can be created, listed, read, renamed, and deleted with curl, with ownership enforced.
- **Dependencies:** NU-024, NU-018 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/conversations/{application,api}/**` (non-streaming parts), `backend/tests/{unit,integration}/conversations/**`.
- **Ownership:** conversations; `api/schemas.py` serialized.
- **Domain:** use cases per section 4.8.
- **Contracts:** endpoints, schemas, codes per section 6.2; `summary_state` is `null` until NU-033.
- **Security:** ownership kit applied to every endpoint; 404 for foreign ids; title length validated.
- **Reliability:** delete is idempotent (second call 404); delete during a stream returns 409 `stream_in_progress`.
- **Steps:** use cases test-first; routers (in `api/router.py`); ownership tests via the kit.
- **Failure cases:** all codes in the table; invalid cursor; invalid UUID; delete while streaming.
- **Tests:** unit, integration per endpoint, security-tagged ownership matrix.
- **Verify:** `make test-unit test-integration`.
- **Acceptance:** all rows verified; ownership matrix green.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** response schema module for NU-026 and NU-028.
- **Reason:** non-streaming endpoints first give the frontend something to build against while streaming is finished.
- **Practices:** OWASP ASVS access control.
- **Status:** not started

#### NU-026 SendMessage streaming use case, SSE encoder, endpoint, limits, stop and failure handling
- **Phase:** 8 · **Context:** conversations
- **Objective:** `SendMessage` use case implementing ARCHITECTURE.md section 7.2 steps 1 to 7 (without research, which NU-030 adds behind the same structure); `platform/sse.py` encoder producing exact event frames and pings; endpoint `POST /conversations/{id}/messages`; per-user concurrency slot and hourly reply limit in `platform/ratelimit.py`; disconnect detection → `stopped`; adapter failure → `failed`; startup reconciliation task marking stale streaming messages failed (R-37).
- **Outcome:** A reply streams from the fake model into a persisted conversation; stop and failure states persist correctly.
- **Dependencies:** NU-025, NU-021 · **Prerequisites:** fake model container.
- **Files:** `backend/src/nuroli/conversations/application/send_message.py`, `backend/src/nuroli/conversations/api/{router,stream}.py`, `backend/src/nuroli/platform/{sse,ratelimit,lifespan}.py`, `backend/tests/{unit,integration,contract}/conversations/**`.
- **Ownership:** conversations and platform.
- **Domain:** `start_reply`, `append_delta`, `complete`, `stop`, `fail`.
- **Contracts:** event names and payloads per section 7.2 byte-for-byte (contract test against documented examples); codes `stream_in_progress`, `rate_limited`, `payload_too_large`.
- **Security:** limits enforced before any model call; the per-user slot is the one shared by every model-backed operation (ARCHITECTURE.md section 17); content length validated; the user message is persisted before the model call so nothing is lost; no model output is interpreted as instructions; `X-Accel-Buffering: no` header set.
- **Reliability:** slot released in `finally`; commit after row creation and after finalization; disconnect mid-stream persists partial text; adapter failure persists partial text with `failed`; ping every 15 seconds; a crash simulation (kill the generator) leaves a `streaming` row that reconciliation fixes.
- **Steps:** SSE encoder with contract test; use case test-first with `FakeChatModel` scripts (success, failure, hang); endpoint; limits; reconciliation; integration tests through the ASGI client reading the stream.
- **Failure cases:** second concurrent send (409); 61st reply in an hour (429 with `Retry-After`); model 401 → `error` event with `model_unavailable`; first-token timeout → `model_timeout`; client disconnect → `stopped` and no further writes.
- **Tests:** unit (use case state transitions), contract (frame format), integration (full stream through the app with the fake adapter; disconnect simulation; limits), security-tagged (limits before model call, asserted by fake call count).
- **Verify:** `make test-unit test-contract test-integration`; curl streaming demo in evidence.
- **Acceptance:** each lifecycle step in section 7.2 has a test; frames match the documented examples exactly.
- **Done:** standard · **Reviewer evidence:** standard plus the raw curl stream capture.
- **Handoff:** the reply pipeline structure that NU-027 reuses and NU-030 extends.
- **Reason:** streaming is the highest-complexity piece; isolating it from research and UI keeps failure handling reviewable.
- **Practices:** test-first; reliability checks.
- **Status:** not started

#### NU-027 RetryReply
- **Phase:** 8 · **Context:** conversations
- **Objective:** `RetryReply` use case and endpoint `POST /conversations/{id}/messages/{user_message_id}/retry` reusing the NU-026 pipeline; validity rule: the latest reply to that user message is `failed` or `stopped`; `superseded` semantics per R-20.
- **Outcome:** Failed or stopped replies can be retried without editing history.
- **Dependencies:** NU-026 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/conversations/application/retry_reply.py`, `backend/src/nuroli/conversations/api/stream.py`, tests.
- **Ownership:** conversations.
- **Domain:** `start_reply(replies_to=...)`.
- **Contracts:** endpoint per section 6.2; `invalid_state` when the latest reply is complete or streaming.
- **Security:** ownership; limits apply as for send.
- **Reliability:** as NU-026.
- **Steps:** use case test-first; endpoint; tests.
- **Failure cases:** retry of a complete reply; retry of a message in another user's conversation; retry while streaming.
- **Tests:** unit, integration, ownership.
- **Verify:** `make test-unit test-integration`.
- **Acceptance:** superseded flag computed correctly after a successful retry (verified through `GET /conversations/{id}`).
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** none.
- **Reason:** small, separate ticket so the retry rule is reviewed on its own.
- **Practices:** test-first.
- **Status:** not started

#### NU-028 Frontend conversations: list, thread, composer, SSE client, streaming, stop, retry, Markdown
- **Phase:** 8 · **Context:** frontend conversations
- **Objective:** `features/conversations` per DESIGN.html sections 4, 7, 8, 14, 15: list with pills, new-conversation state, thread rendering with meta lines and model name, composer with persistence and limits, `api/sse.ts` parser, streaming render with jump-to-latest, stop (abort), retry, failed and stopped states, superseded collapse, rename and delete dialog, sanitized Markdown component (R-38), live-region announcements, mobile layout.
- **Outcome:** The first full user slice: sign in, ask, watch the answer stream, stop, retry, reopen later.
- **Dependencies:** NU-027, NU-016, NU-022 · **Prerequisites:** none.
- **Files:** `frontend/src/features/conversations/**` (including `types.ts`), `frontend/src/api/sse.ts`, `frontend/src/components/{Markdown,Message,Composer,Drawer,Dialog}.tsx`, `frontend/tests/e2e/conversations.spec.ts`.
- **Ownership:** frontend conversations; `frontend/src/api/` serialized.
- **Domain:** none.
- **Contracts:** endpoints and events per ARCHITECTURE.md sections 6.2 and 7.
- **Security:** Markdown through rehype-sanitize with the documented schema; link protocol filter; no `dangerouslySetInnerHTML`; error text from the envelope only.
- **Reliability:** SSE parser handles split frames and pings; a closed stream without `end` shows retry; composer text survives reload; refetch after terminal event.
- **Steps:** SSE parser with unit tests (split chunks, pings, unknown events ignored); Markdown component with sanitization tests (script, iframe, `javascript:` link, image dropped); hooks with MSW; screens; e2e using fake-model triggers for stop, failure, and length.
- **Failure cases:** every row in DESIGN.html section 7 table.
- **Tests:** Vitest (parser, Markdown, hooks), e2e (send and stream, stop keeps partial text, retry after `[[error500]]`, rename, delete dialog, keyboard-only send and stop, axe at both widths).
- **Verify:** `make test-fe e2e`.
- **Acceptance:** e2e journeys pass; sanitization tests pass; live region announces start and end.
- **Done:** standard · **Reviewer evidence:** standard plus screenshots of streaming, stopped, and failed states.
- **Handoff:** `Message` and `Markdown` components for NU-031, NU-035, NU-038.
- **Reason:** completes the conversation vertical slice end to end before research or knowledge features begin.
- **Practices:** WCAG with axe; adapter contract tests (MSW); OWASP safe rendering.
- **Status:** not started

### Phase 9 — Web research and sources

#### NU-029 WebSearchPort, FakeWebSearch, Tavily adapter, research settings
- **Phase:** 9 · **Context:** ports / adapters
- **Objective:** `WebSearchPort` in `nuroli/ports/web_search.py`; `FakeWebSearch`; `adapters/tavily.py` per ARCHITECTURE.md section 12 (basic depth, 5 results, 10 s timeout, sanitizer applied, base URL from `NUROLI_TAVILY_BASE_URL`); provider factory (`none` or `tavily`); `research_enabled` in capabilities.
- **Outcome:** Search results arrive as sanitized `Source` lists or research is cleanly disabled.
- **Dependencies:** NU-021 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/ports/web_search.py`, `backend/src/nuroli/adapters/{tavily,fakes}.py`, `backend/src/nuroli/platform/{providers,settings}.py`, `backend/tests/contract/test_tavily.py`, `backend/tests/contract/fixtures/tavily/*.json`, `.env.example`.
- **Ownership:** `ports/` serialized; adapters; platform.
- **Domain:** none.
- **Contracts:** port per section 4.5; settings `NUROLI_SEARCH_PROVIDER`, `NUROLI_TAVILY_API_KEY`, `NUROLI_TAVILY_BASE_URL`.
- **Security:** key only in the request header; results sanitized (https only); the adapter never follows result URLs; provider host fixed from settings.
- **Reliability:** timeout and non-200 map to an empty result with a logged warning and `reason=failed`; never raises into the reply pipeline.
- **Steps:** contract tests from recorded responses (success, empty, 401, 429, timeout, malformed); implement; factory; capabilities.
- **Failure cases:** as listed; provider `tavily` without key fails at startup (NU-009 rule).
- **Tests:** contract, unit (factory), integration (capabilities flag).
- **Verify:** `make test-contract test-unit test-integration`.
- **Acceptance:** all fixtures pass; disabled mode returns `enabled=False`.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** port method signatures for NU-030.
- **Reason:** R-07 and R-08 make search a narrow, replaceable adapter; proving it against recorded responses keeps tests free.
- **Practices:** adapter contract tests.
- **Status:** not started

#### NU-030 Research inside SendMessage: query rewrite, search, sources, research events, search limit
- **Phase:** 9 · **Context:** conversations
- **Objective:** Extend `SendMessage` and `RetryReply` per R-09 and ARCHITECTURE.md section 7.2 step 2: when `research=true` and enabled, call `complete` with `ResearchQueryPrompt`, search, sanitize, `attach_sources`, emit `research` and `sources` events, include the untrusted research block in the model context; `research_unavailable` when disabled; per-user hourly search limit; skip reasons.
- **Outcome:** Replies can carry clickable, sanitized sources from a real search API.
- **Dependencies:** NU-029, NU-027 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/conversations/application/{send_message,retry_reply,research.py}`, `backend/src/nuroli/conversations/domain/prompts.py`, tests.
- **Ownership:** conversations.
- **Domain:** `attach_sources`, `research_query` on the assistant message, prompt block.
- **Contracts:** events per section 7.2; `research_query` and `sources` on the message schema.
- **Security:** snippets enter the prompt only inside the delimited untrusted block (test with a snippet containing "ignore previous instructions" asserts the block delimiters and that the system prompt precedes it); the source list attached to the message comes from the search results only; the rewritten query is length-limited (200 characters) and logged only as a hash.
- **Reliability:** search or rewrite failure emits `research skipped` and the reply continues; the rewrite call has its own 20 s timeout and counts toward the reply limit, not the search limit.
- **Steps:** test-first with `FakeChatModel` and `FakeWebSearch`; implement; integration through the stream.
- **Failure cases:** disabled provider with `research=true` (409 before stream); 31st search in an hour (skipped with `rate_limited`, reply continues); empty results (sources omitted, `result_count: 0`); rewrite returns garbage (fallback to the raw message truncated).
- **Tests:** unit (event order, skip paths, prompt injection fixture), integration (stream with sources), security-tagged.
- **Verify:** `make test-unit test-integration`.
- **Acceptance:** event order `start, research, sources, delta…, end` verified; injection fixture test passes; skip paths never fail the reply.
- **Done:** standard · **Reviewer evidence:** standard plus the prompt block sample from a test.
- **Handoff:** message `sources` shape for NU-031 and draft generation in NU-034.
- **Reason:** research is a bounded extension of the reply pipeline; adding it after streaming is stable keeps the risk local.
- **Practices:** OWASP LLM prompt-injection sheet; test-first.
- **Status:** not started

#### NU-031 Frontend research toggle, progress, sources block, source drawer
- **Phase:** 9 · **Context:** frontend conversations
- **Objective:** Per DESIGN.html section 9: toggle (hidden when disabled, remembered per conversation), research status line from `research` events, sources block under replies, source drawer or bottom sheet with focus management, Researched pill.
- **Outcome:** Users can ask for research and inspect sources without losing their place.
- **Dependencies:** NU-030, NU-028 · **Prerequisites:** test stack with `NUROLI_SEARCH_PROVIDER=tavily` and `NUROLI_TAVILY_BASE_URL` pointing at the fake container (NU-022); no test-only code path exists in the API.
- **Files:** `frontend/src/features/conversations/**` (research parts), `frontend/src/components/{Sources,SourceDrawer}.tsx`, `compose.test.yaml` (search variables only), e2e spec.
- **Ownership:** frontend conversations; compose serialized.
- **Domain:** none.
- **Contracts:** events and schema from NU-030.
- **Security:** links rendered with the documented `rel` and `target`; URLs come only from the API's `sources` list; snippet text rendered as text.
- **Reliability:** drawer state survives new deltas; scroll position preserved.
- **Steps:** components with tests; hook wiring; e2e using the fake search triggers.
- **Failure cases:** research skipped reasons rendered; no results text.
- **Tests:** Vitest (render of each research status), e2e (toggle, sources appear before text, drawer opens and returns focus, keyboard, axe).
- **Verify:** `make test-fe e2e`.
- **Acceptance:** DESIGN.html section 9 rows verified.
- **Done:** standard · **Reviewer evidence:** standard plus screenshots.
- **Handoff:** `Sources` component reused by summaries.
- **Reason:** completes the research slice visibly.
- **Practices:** WCAG with axe.
- **Status:** not started

### Phase 10 — Summary review and confirmation

#### NU-032 Knowledge domain: Summary aggregate, Draft, versions, state machine, prompts
- **Phase:** 10 · **Context:** knowledge
- **Objective:** `knowledge/domain/`: `Summary` aggregate (`start_draft(content, generated_by, sources, now)`, `update_draft(title, body, expected_revision)`, `confirm(expected_revision, now)`, `discard_draft()`, `archive()`, `unarchive()`), `Draft` value object, `SummaryVersion` entity, state machine per ARCHITECTURE.md section 4.3, `SummaryPrompt` and `KnowledgeAnswerPrompt` domain services, `ConversationTranscriptPort` protocol in `knowledge/application/ports.py`.
- **Outcome:** Confirmation-before-save and versioning rules are testable in isolation.
- **Dependencies:** NU-007 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/knowledge/domain/**`, `backend/src/nuroli/knowledge/application/ports.py`, `backend/tests/unit/knowledge/**`.
- **Ownership:** knowledge; ports serialized.
- **Domain:** all of section 4.3 (Summary).
- **Contracts:** revision semantics; state transitions; prompt text snapshots.
- **Security:** sources on a version are copied from the draft, never from user-editable input; the answer prompt marks summaries as untrusted data and instructs citation by marker.
- **Reliability:** pure code.
- **Steps:** test-first for every transition and invariant; implement.
- **Failure cases:** confirm without draft; stale revision; archive a draft-only summary; unarchive a confirmed summary; second confirm; body over 50,000; title empty.
- **Tests:** one per transition and invariant; prompt snapshots.
- **Verify:** `make test-unit`.
- **Acceptance:** state machine diagram in ARCHITECTURE.md section 4.3 fully covered.
- **Done:** standard · **Reviewer evidence:** standard plus transition-to-test mapping.
- **Handoff:** method signatures for NU-034.
- **Reason:** the confirmation rule is a product promise; it lives in one aggregate with exhaustive tests.
- **Practices:** test-first.
- **Status:** not started

#### NU-033 Summaries tables, repository with search vector, transcript port, deletion semantics
- **Phase:** 10 · **Context:** knowledge / conversations
- **Objective:** Migration 0004 `summaries` and `summary_versions` per ARCHITECTURE.md section 10 including `search_vector` and GIN index; `SummaryRepository` (`add`, `get_owned`, `get_by_conversation`, `list_owned` with state, query, cursor, `save` updating `search_vector` when the current version changes or state moves to or from archived, `delete`); `search_confirmed` implemented per section 13; `ConversationTranscriptPort` implementation in `conversations/infrastructure/transcript.py`; `summary_state` join in the conversation list; R-32 behavior on conversation delete (FK `on delete set null`, draft-only summary deleted by the `DeleteConversation` use case).
- **Outcome:** Summaries persist, are searchable when confirmed, and survive conversation deletion.
- **Dependencies:** NU-032, NU-024 · **Prerequisites:** dev stack.
- **Files:** `backend/migrations/versions/0004_*.py`, `backend/src/nuroli/knowledge/infrastructure/**`, `backend/src/nuroli/conversations/infrastructure/{transcript,repositories}.py`, `backend/src/nuroli/conversations/application/delete_conversation.py`, `backend/src/nuroli/platform/wiring.py`, tests, `backend/tests/unit/knowledge/fakes.py`.
- **Ownership:** knowledge; conversations (transcript and delete only); migrations serialized.
- **Domain:** mapping; delete semantics.
- **Contracts:** SQL for the vector and search per section 13; list cursor as NU-024.
- **Security:** `search_confirmed` filters `owner_id` and `state='confirmed'` in the same query (test: another user's confirmed summary and the owner's draft and archived summaries never appear).
- **Reliability:** vector update in the same transaction as confirm; migration includes a one-statement rebuild in its docstring.
- **Steps:** migration; models; mappers; repository; search; transcript port; delete semantics; shared suite; fakes.
- **Failure cases:** `websearch_to_tsquery` with only stop words returns no rows (handled, not an error); unique conversation constraint violation mapped to `invalid_state`.
- **Tests:** shared suite; search ranking sanity (title match outranks body match); exclusion matrix; delete semantics both branches.
- **Verify:** `make migrate-check test-integration test-unit`.
- **Acceptance:** exclusion matrix green; delete semantics green; `summary_state` visible in the conversation list.
- **Done:** standard · **Reviewer evidence:** standard plus `EXPLAIN` of the search query showing the GIN index.
- **Handoff:** `search_confirmed` result shape for NU-037.
- **Reason:** the index is written at confirm time by the same repository, which is what makes summary-only retrieval a structural guarantee.
- **Practices:** PostgreSQL rules.
- **Status:** not started

#### NU-034 Summary use cases and endpoints: generate, get, update draft, confirm, discard, archive, list, versions
- **Phase:** 10 · **Context:** knowledge
- **Objective:** Use cases `GenerateDraft` (transcript through the port, `complete` with `SummaryPrompt`, parse title and body, copy sources from assistant messages, R-31 overwrite), `GetSummary`, `UpdateDraft`, `ConfirmSummary`, `DiscardDraft`, `ArchiveSummary`, `UnarchiveSummary`, `ListSummaries`, `GetVersion`; all endpoints in ARCHITECTURE.md section 6.3 except `/knowledge/ask`; hourly generation counted under the reply limit.
- **Outcome:** The whole capture loop works with curl.
- **Dependencies:** NU-033, NU-021, NU-018 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/knowledge/{application,api}/**`, tests.
- **Ownership:** knowledge; schemas serialized.
- **Domain:** use cases per section 4.8.
- **Contracts:** endpoints, bodies, codes per section 6.3; draft revision semantics.
- **Security:** ownership kit on every endpoint; model output parsed as text (title line and body) with length limits, never executed or rendered server-side; sources never accepted from the request body.
- **Reliability:** generation takes the per-user model slot and is bounded by the model timeout (409 `stream_in_progress` while a reply streams); failure leaves the previous draft untouched; confirm idempotency (second confirm 409 `no_draft`).
- **Steps:** use cases test-first with fakes; routers; integration; ownership matrix.
- **Failure cases:** all codes in section 6.3; generation on a conversation with no complete reply; model returns no title (fallback to conversation title).
- **Tests:** unit, integration per endpoint, security-tagged ownership, reliability (failed generation preserves draft).
- **Verify:** `make test-unit test-integration`.
- **Acceptance:** all rows verified; a fact present only in a draft is not returned by `search_confirmed` (integration test reused from NU-033).
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** schema module for NU-035 and NU-036.
- **Reason:** completes the backend of the confirmation loop in one reviewable unit.
- **Practices:** test-first; OWASP ASVS access control.
- **Status:** not started

#### NU-035 Frontend summary review: generate, edit with autosave, confirm, discard, regenerate, versions
- **Phase:** 10 · **Context:** frontend summaries
- **Objective:** `/c/:id/summary` per DESIGN.html section 10: generation progress, split layout and mobile sheet, title and Markdown editor with preview, 800 ms autosave with revision and stale handling, Save to library with success state and double-submit guard, Back keeps draft, Discard and Regenerate dialogs, Summarize entry in the thread header with the in-progress hint, edit-a-saved-summary entry.
- **Outcome:** The capture loop works in the browser.
- **Dependencies:** NU-034, NU-031 · **Prerequisites:** none.
- **Files:** `frontend/src/features/summaries/**`, `frontend/src/features/conversations/ThreadHeader.tsx`, e2e spec.
- **Ownership:** frontend summaries; one file in conversations (header) coordinated.
- **Domain:** none.
- **Contracts:** endpoints per section 6.3.
- **Security:** editor content sent as text; preview through the sanitized Markdown component; sources displayed read-only.
- **Reliability:** autosave failures show inline and keep local text; stale revision reloads with notice; navigating away and back restores the draft from the server.
- **Steps:** hooks with MSW; screens; dialogs; e2e.
- **Failure cases:** rows in DESIGN.html section 10 table.
- **Tests:** Vitest (autosave debounce, stale handling, double submit), e2e (generate, edit, back, resume, confirm creates exactly one library entry, three rapid clicks create one entry, discard, regenerate dialog, mobile layout, keyboard, axe).
- **Verify:** `make test-fe e2e`.
- **Acceptance:** e2e journeys pass; exactly-one-entry test passes.
- **Done:** standard · **Reviewer evidence:** standard plus screenshots at both widths.
- **Handoff:** editor component for later edits.
- **Reason:** confirmation-before-save is a product promise that must be visibly correct in the UI, including double submit.
- **Practices:** WCAG with axe.
- **Status:** not started

#### NU-036 Frontend library: list, search, archive, detail, versions, reopen conversation
- **Phase:** 10 · **Context:** frontend summaries
- **Objective:** `/library` and `/library/:id` per DESIGN.html section 11: cards, search with debounce, show-archived filter, load more, detail with rendered body and sources, Edit, Archive and Unarchive, versions list, open conversation, deleted-conversation state, empty states.
- **Outcome:** Saved knowledge is browsable and leads back to its conversation.
- **Dependencies:** NU-035 · **Prerequisites:** none.
- **Files:** `frontend/src/features/summaries/Library*.tsx`, hooks, e2e spec.
- **Ownership:** frontend summaries.
- **Domain:** none.
- **Contracts:** list and detail endpoints per section 6.3.
- **Security:** sanitized rendering; no client-side state decides confirmation.
- **Reliability:** pagination stable under new saves; search clears correctly.
- **Steps:** hooks; screens; e2e.
- **Failure cases:** rows in DESIGN.html section 11 table.
- **Tests:** Vitest, e2e (save then find, search no-results, archive removes from default list and appears under archived, reopen conversation, deleted-conversation state via API delete, axe, keyboard shortcut to search).
- **Verify:** `make test-fe e2e`.
- **Acceptance:** all rows verified.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** none.
- **Reason:** closes the capture slice with the library and the path back to the source.
- **Practices:** WCAG with axe.
- **Status:** not started

### Phase 11 — Knowledge retrieval

#### NU-037 AskKnowledge streaming use case and endpoint
- **Phase:** 11 · **Context:** knowledge
- **Objective:** `AskKnowledge` per ARCHITECTURE.md sections 7.3, 13, and R-17: `search_confirmed` (R-39 top 5), gate on results, `KnowledgeAnswerPrompt` with numbered summaries truncated to the budget, stream via the SSE encoder with `citations` first; endpoint `POST /knowledge/ask`; counted under the reply limit; answers not stored (R-33).
- **Outcome:** Questions over saved knowledge are answered with citations, or honestly declined without a model call.
- **Dependencies:** NU-034, NU-026 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/knowledge/application/ask_knowledge.py`, `backend/src/nuroli/knowledge/api/ask.py`, tests.
- **Ownership:** knowledge.
- **Domain:** `KnowledgeAnswerPrompt`.
- **Contracts:** events per section 7.3; citation objects.
- **Security:** ownership through `search_confirmed`; drafts, archived, transcripts, and other users' summaries excluded (matrix test through the endpoint); no web search on this path (asserted: `FakeWebSearch.calls` empty); the model receives summaries only inside the untrusted block.
- **Reliability:** empty results → no model call (asserted by fake call count); model failure → `error` event; limits and the per-user slot as for replies.
- **Steps:** use case test-first; endpoint; integration.
- **Failure cases:** no matches; stop-word-only question; model timeout; rate limit.
- **Tests:** unit, integration (stream), security-tagged exclusion matrix and no-web-search assertion.
- **Verify:** `make test-unit test-integration`.
- **Acceptance:** a fact present only in a raw conversation or a draft never appears in an answer (integration test seeds all three and asks).
- **Done:** standard · **Reviewer evidence:** standard plus the exclusion matrix output.
- **Handoff:** citation shape for NU-038.
- **Reason:** summary-only retrieval is the product's defining rule; this ticket proves it end to end on the server.
- **Practices:** test-first; OWASP LLM prompt-injection sheet.
- **Status:** not started

#### NU-038 Frontend Ask my knowledge
- **Phase:** 11 · **Context:** frontend knowledge
- **Objective:** `/ask` per DESIGN.html section 12: question field, streaming answer with citation chips, cited summaries card with links to summary and conversation, insufficient-evidence state with the research handoff (new conversation pre-filled, research on when available), empty-library state, errors.
- **Outcome:** The learning loop closes in the browser.
- **Dependencies:** NU-037, NU-036 · **Prerequisites:** none.
- **Files:** `frontend/src/features/knowledge/**`, e2e spec.
- **Ownership:** frontend knowledge.
- **Domain:** none.
- **Contracts:** events per section 7.3.
- **Security:** citations rendered from the `citations` event only; marker chips map to ids from that event; no web content on this screen.
- **Reliability:** same SSE handling as replies.
- **Steps:** hooks; screen; e2e.
- **Failure cases:** rows in DESIGN.html section 12 table.
- **Tests:** Vitest (marker to citation mapping, insufficient state), e2e (save a summary, ask, follow citation to summary and conversation; ask something uncovered, see insufficient state, start research conversation; axe; keyboard).
- **Verify:** `make test-fe e2e`.
- **Acceptance:** all rows verified; full loop e2e passes (sign in → ask → research → summarize → confirm → library → ask knowledge → open summary → reopen conversation).
- **Done:** standard · **Reviewer evidence:** standard plus the full-loop e2e log.
- **Handoff:** none.
- **Reason:** the last feature slice; its e2e is the product's acceptance journey.
- **Practices:** WCAG with axe.
- **Status:** not started

### Phase 12 — Docker Compose release

#### NU-039 Release images, production nginx, README installation guide, release stack e2e
- **Phase:** 12 · **Context:** infra
- **Objective:** Harden `api.Dockerfile` and `web.Dockerfile` (pinned digests, non-root, no build tools in final stage, `HEALTHCHECK`); `compose.yaml` referencing `ghcr.io/amirhosseinsaloot/nuroli-api:${NUROLI_VERSION}` and `ghcr.io/amirhosseinsaloot/nuroli-web:${NUROLI_VERSION}`; nginx production config with CSP and SSE timeouts; README install guide per DESIGN.html section 5 (prerequisites, `.env`, `docker compose up -d`, first account, check-model, local model runtime note, HTTPS proxy note, cookie-secure warning); `make e2e-release` running the Playwright suite against the release stack built locally.
- **Outcome:** An operator can install from the README alone.
- **Dependencies:** NU-038, NU-022 · **Prerequisites:** none.
- **Files:** `infra/**`, `compose.yaml`, `README.md`, `make/infra.mk`, e2e config.
- **Ownership:** serialized (infra, compose, README).
- **Domain:** none.
- **Contracts:** ARCHITECTURE.md section 15.
- **Security:** `docker history` shows no secrets; Trivy clean locally; CSP blocks inline scripts (e2e checks the header and that the app works under it); only the web port published.
- **Reliability:** restart policies; `db` volume survives `docker compose down` and `up`; e2e-release passes.
- **Steps:** Dockerfiles; compose; nginx; README; target; run.
- **Failure cases:** missing `NUROLI_VERSION` defaults to `latest` with a README warning to pin.
- **Tests:** e2e-release; volume persistence script; header checks.
- **Verify:** `make up && make e2e-release && make down && make up` then data still present.
- **Acceptance:** fresh-machine install following README only (reviewer performs it in a clean VM or container and records steps).
- **Done:** standard · **Reviewer evidence:** standard plus the clean-install log.
- **Handoff:** image names for NU-040.
- **Reason:** the product is a Compose install; the README is part of the product.
- **Practices:** reliability checks.
- **Status:** not started

#### NU-040 Release workflow: tag, build, scan, publish
- **Phase:** 12 · **Context:** infra
- **Objective:** `.github/workflows/release.yml` per section 5.5: on `v*` tags, build both images, Trivy scan failing on high or critical, push to GHCR with tag and digest, create the GitHub release with `compose.yaml` and `.env.example` attached; branch protection documentation for `rebuild/v1` and `master`.
- **Outcome:** Versioned, scanned images that `compose.yaml` pulls.
- **Dependencies:** NU-039 · **Prerequisites:** GHCR enabled.
- **Files:** `.github/workflows/release.yml`, `README.md` (release section).
- **Ownership:** serialized.
- **Domain:** none.
- **Contracts:** image names and tags; `permissions: packages: write` only in this workflow.
- **Security:** actions pinned by SHA; `GITHUB_TOKEN` only; no provider keys.
- **Reliability:** the workflow runs from the commit that passed the pull-request gate (tags only on `rebuild/v1` or `master` heads, checked in the workflow).
- **Steps:** workflow; test with a pre-release tag `v0.0.1-rc1`; README.
- **Failure cases:** Trivy finding → workflow fails with the report attached.
- **Tests:** the rc tag run.
- **Verify:** a successful rc release visible in GHCR; `NUROLI_VERSION=v0.0.1-rc1 make up` works on a clean host.
- **Acceptance:** rc published and installable.
- **Done:** standard · **Reviewer evidence:** standard plus workflow run link.
- **Handoff:** none.
- **Reason:** releases must be reproducible artifacts, not local builds.
- **Practices:** Conventional Commits (tags derive from them); dependency and vulnerability checks.
- **Status:** not started

### Phase 13 — Reliability, backup, and recovery

#### NU-041 Backup, restore, restore drill, startup reconciliation, graceful shutdown
- **Phase:** 13 · **Context:** platform / infra
- **Objective:** `make backup` and `make restore FILE=` per ARCHITECTURE.md section 19; `scripts/restore-drill.sh` that backs up, wipes a scratch stack, restores, and runs a smoke query; uvicorn graceful shutdown finalizing in-flight streams as `failed` with `server_shutdown`; startup reconciliation verified after a forced kill; README operations section.
- **Outcome:** Data can be recovered and crashes leave honest state.
- **Dependencies:** NU-039 · **Prerequisites:** none.
- **Files:** `make/infra.mk`, `scripts/**`, `backend/src/nuroli/platform/lifespan.py`, `README.md`, tests.
- **Ownership:** serialized (scripts, README); platform.
- **Domain:** none.
- **Contracts:** backup file naming `backups/nuroli-<timestamp>.dump`.
- **Security:** backups contain user data; README states where they live and that they must be protected; `backups/` ignored by git.
- **Reliability:** drill script exits non-zero on any step failure; shutdown waits at most 10 s.
- **Steps:** targets; drill; lifespan; tests; README.
- **Failure cases:** restore into a running stack refused; missing file.
- **Tests:** integration: kill the API during a stream (test stack) and assert the message is `failed` after restart; drill run in CI as part of `e2e` job (fast, small data).
- **Verify:** `make backup && scripts/restore-drill.sh`.
- **Acceptance:** drill passes in CI; kill test passes.
- **Done:** standard · **Reviewer evidence:** standard plus drill output.
- **Handoff:** none.
- **Reason:** a self-hosted product without a proven restore is not production-ready.
- **Practices:** reliability checks.
- **Status:** not started

#### NU-042 Logging completeness, redaction tests, readiness semantics
- **Phase:** 13 · **Context:** platform
- **Objective:** One request log line per request with the documented fields; model and search call logs; redaction tests over captured logs from the full e2e run (no emails beyond the prefix, no message content, no tokens, no keys); `/ready` purge scheduling; log level per settings.
- **Outcome:** Operators can diagnose without reading user content.
- **Dependencies:** NU-041 · **Prerequisites:** none.
- **Files:** `backend/src/nuroli/platform/{logging,middleware}.py`, adapters (log calls), `backend/tests/integration/test_logs.py`, e2e log capture step.
- **Ownership:** platform; adapters (log lines only).
- **Domain:** none.
- **Contracts:** field names per ARCHITECTURE.md section 19.
- **Security:** redaction asserted by scanning the whole e2e log for seeded secrets and message text.
- **Reliability:** logging failures never break requests.
- **Steps:** fields; tests; scanner in `make e2e`.
- **Failure cases:** n/a.
- **Tests:** integration and the e2e scanner.
- **Verify:** `make test-integration e2e`.
- **Acceptance:** scanner finds none of the seeded sensitive strings.
- **Done:** standard · **Reviewer evidence:** standard.
- **Handoff:** none.
- **Reason:** logs are the only observability in v1; they must be safe to share.
- **Practices:** OWASP ASVS logging items.
- **Status:** not started

### Phase 14 — Setup quality gates and release hardening

#### NU-043 Security test consolidation and gates
- **Phase:** 14 · **Context:** platform / all
- **Objective:** A `security` pytest marker and Playwright tag collecting: full cross-user 404 matrix over every owned endpoint (generated from the OpenAPI document so new endpoints cannot be missed), CSRF and cookie attribute checks, throttle and limit checks, prompt-injection fixtures (snippets and summaries containing instructions) asserting placement inside untrusted blocks, sanitization checks, secret absence in logs and images; `make audit` required in CI already; Trivy on release; a `SECURITY.md` describing the boundaries and how to report issues.
- **Outcome:** The security promises in ARCHITECTURE.md section 17 are executable checks.
- **Dependencies:** NU-042 · **Prerequisites:** none.
- **Files:** `backend/tests/security/**`, `frontend/tests/e2e/security.spec.ts`, `SECURITY.md`, `make/backend.mk` (`test-security`), `.github/workflows/backend.yml` (`security` job).
- **Ownership:** serialized (`.github`); tests.
- **Domain:** none.
- **Contracts:** OpenAPI-driven matrix must cover 100 percent of endpoints with an `{id}` path parameter (asserted).
- **Security:** this ticket is the gate.
- **Reliability:** n/a.
- **Steps:** matrix generator; fixtures; tags; CI job `security` required.
- **Failure cases:** a new endpoint without ownership fails the matrix.
- **Tests:** as listed.
- **Verify:** `make test-security`.
- **Acceptance:** matrix covers all owned endpoints; all checks green; `SECURITY.md` present.
- **Done:** standard · **Reviewer evidence:** standard plus the matrix coverage output.
- **Handoff:** none.
- **Reason:** consolidating security checks into one required job makes regressions visible regardless of which ticket introduces them.
- **Practices:** OWASP ASVS; LLM prompt-injection sheet.
- **Status:** not started

#### NU-044 Accessibility and keyboard gates
- **Phase:** 14 · **Context:** frontend
- **Objective:** axe checks on every route at 1440px and 390px in one spec; keyboard-only journey through the full loop; reduced-motion assertion; focus management assertions from DESIGN.html section 16; zoom 200 percent layout check.
- **Outcome:** WCAG 2.2 AA is a gate, not a hope.
- **Dependencies:** NU-038 · **Prerequisites:** none.
- **Files:** `frontend/tests/e2e/a11y.spec.ts`, fixes inside `frontend/src/**` limited to accessibility attributes and focus handling.
- **Ownership:** frontend (accessibility fixes anywhere in `frontend/src`, coordinated so no other frontend ticket is open).
- **Domain:** none.
- **Contracts:** DESIGN.html section 16 table.
- **Security:** none.
- **Reliability:** n/a.
- **Steps:** spec; fix violations; document exceptions with reasons (none expected).
- **Failure cases:** any axe violation fails.
- **Tests:** the spec.
- **Verify:** `make e2e`.
- **Acceptance:** zero violations; keyboard journey passes.
- **Done:** standard · **Reviewer evidence:** standard plus axe summary.
- **Handoff:** none.
- **Reason:** accessibility regressions are cheap to prevent with one always-on spec.
- **Practices:** WCAG with axe.
- **Status:** not started

#### NU-045 Upgrade test, release checklist, rollback documentation, final README
- **Phase:** 14 · **Context:** infra / docs
- **Objective:** `scripts/upgrade-test.sh` installing the previous tag with seeded data, upgrading to the candidate, and running the smoke journey; release checklist in README per section 5.6; rollback steps; final README pass (install, operate, backup, upgrade, troubleshoot, security notes); `release.yml` runs the upgrade test.
- **Outcome:** Releases are upgrade-safe and documented.
- **Dependencies:** NU-040, NU-041, NU-043, NU-044 · **Prerequisites:** at least one published rc tag.
- **Files:** `scripts/upgrade-test.sh`, `README.md`, `.github/workflows/release.yml`.
- **Ownership:** serialized.
- **Domain:** none.
- **Contracts:** checklist items per section 5.6.
- **Security:** none new.
- **Reliability:** upgrade test blocks release.
- **Steps:** script; workflow; README.
- **Failure cases:** irreversible migration detected (downgrade fails) → release blocked.
- **Tests:** the script in the release workflow.
- **Verify:** `scripts/upgrade-test.sh v0.0.1-rc1 <candidate>`.
- **Acceptance:** rc2 released through the full gate.
- **Done:** standard · **Reviewer evidence:** standard plus workflow run.
- **Handoff:** v1.0.0 tag readiness statement.
- **Reason:** the last hardening step before v1 is proving that the next release will not break an install.
- **Practices:** release and rollback checks.
- **Status:** not started

### Phase 15 — Future extensions (not ready; decisions required)

These tickets are placeholders so the extension points stay visible. Each is
**not ready** and must not be assigned until the product owner records the
decisions it names in ARCHITECTURE.md.

#### NU-046 Multiple model connections and per-reply choice — not ready
- **Context:** conversations / platform · **Depends on:** v1 release.
- **Decisions required:** connection storage (env versus table), UI for choice, default model policy, protocol list.
- **Extension point:** ARCHITECTURE.md section 22.1.
- **Reason:** deferred by R-01 and R-06; recorded so no one adds a partial registry early.

#### NU-047 Hosted accounts, credits, and billing — not ready
- **Context:** identity / platform · **Depends on:** v1 release.
- **Decisions required:** pricing semantics, payment provider, accounting model, budget enforcement, SMTP flows (verification and reset), account linking policy.
- **Extension point:** ARCHITECTURE.md section 22.2.
- **Reason:** deferred by R-01; usage columns already exist.

#### NU-048 Mobile client bearer sessions — not ready
- **Context:** identity · **Depends on:** v1 release.
- **Decisions required:** token delivery variant, refresh policy, device revocation UI.
- **Extension point:** ARCHITECTURE.md section 5.4.
- **Reason:** deferred by R-01; the sessions table already supports it.

---

## 9. Phase exit criteria

| Phase | Exit evidence |
| --- | --- |
| 1 | Clean clone: `make setup` and `make check` pass with only the tooling in place; pull-request gate green; a commit refreshes `graphify-out/graph.json` through the hook |
| 2 | Boundary lint rejects a forbidden import; shell renders at both widths with axe clean; `make preflight` produces impact and conflict reports and the CI graph job is green |
| 3 | Misconfiguration fails fast; `make up` serves `/health` through nginx with security headers |
| 4 | `/ready` reflects migrations; CI runs against PostgreSQL; two API starts do not race |
| 5 | Register, sign in (both methods), sign out in the browser; operator reset works |
| 6 | Cross-user access returns 404 everywhere tested; CSRF and throttling enforced; forced password change works |
| 7 | `make check-model` succeeds against the fake container; adapter contract fixtures all pass |
| 8 | Full conversation slice in the browser with stop, retry, and failure states |
| 9 | Research toggle produces sanitized, clickable sources; injection fixture passes |
| 10 | Capture loop in the browser; exactly one library entry per confirm; drafts never retrievable |
| 11 | Full-loop e2e passes; exclusion matrix green |
| 12 | Clean-machine install from README; rc image published |
| 13 | Restore drill and kill test pass; log scanner clean |
| 14 | Security and accessibility gates required in CI; upgrade test green; rc2 released |
| 15 | Not applicable until decisions are recorded |

---

## 10. Unresolved items

| Item | Owner | Blocks |
| --- | --- | --- |
| Google OAuth client for manual verification | product owner | manual step in NU-015 only |
| Tavily key for one optional live check | product owner | none (contract tests suffice) |
