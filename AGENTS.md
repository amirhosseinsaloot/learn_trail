# AGENTS.md

Entry point for every agent and human who changes this repository. Read this
file first, then only the sections your ticket names. It points to the
planning documents; it does not repeat them.

- Rules, workflow, quality gates, tickets: [docs/rebuild/IMPLEMENTATION.md](docs/rebuild/IMPLEMENTATION.md)
- Decisions (R-01 to R-41) and contracts: [docs/rebuild/ARCHITECTURE.md](docs/rebuild/ARCHITECTURE.md)
- Screens, states, tokens: [docs/rebuild/DESIGN.html](docs/rebuild/DESIGN.html)

## Purpose

Nuroli is a self-hosted learning companion: a user talks with one configured
model, optionally with web research, then reviews and confirms a summary into
a knowledge library that later answers questions with citations. Backend:
Python 3.14, FastAPI, SQLAlchemy async, PostgreSQL. Frontend: React 19,
TypeScript, Vite. Deployment: Docker Compose (web, api, db).

## Commands

Everything runs through `make`; run `make help` for the full list. Required
host tools: `make`, `docker`, `uv`, `pnpm`, `git`. Targets that are not yet
implemented exit 1 and name the ticket that implements them. Every target
prints the commands it runs and honours the worktree file `.worktree.env`.

| Target | Runs |
| --- | --- |
| `make setup` | `uv sync`, `pnpm install --frozen-lockfile`, `pre-commit install`, graphify tool install |
| `make dev` | Compose dev stack: db, api with reload, Vite dev server, fake model |
| `make up` / `make down` | Release stack from `compose.yaml` |
| `make fmt` / `make fmt-check` | Ruff format and Prettier, write or check |
| `make lint` | Ruff lint, import-linter boundaries, ESLint |
| `make typecheck` | Pyright, `tsc --noEmit` |
| `make test-unit` / `test-integration` / `test-contract` / `test-fe` / `e2e` | Test categories (IMPLEMENTATION.md section 5.3) |
| `make migrate` / `migration name=` / `migrate-check` | Alembic upgrade, autogenerate, drift and round-trip check |
| `make audit` | `pip-audit`, `pnpm audit --audit-level=high`, `gitleaks detect` |
| `make check` | The local pull-request gate: fmt-check lint typecheck and every test category |
| `make deps-update` | Dependency updates; run only by the owner (R-40) |
| `make backup` / `make restore FILE=` | Database dump and restore |
| `make check-model` | `nuroli check-model` inside the API container |
| `make worktree T=NU-0nn` / `worktree-clean T=NU-0nn` | Ticket worktree with its own branch, ports, and baseline |
| `make graph-build` / `graph-update` / `graph-watch` | Code graph in `graphify-out/` (R-41) |
| `make graph-impact` / `graph-conflicts` / `graph-overlap` / `preflight` | Blast radius, branch overlap, pre-pull-request checks |

## Rules

1. **One ticket, one branch, one worktree.** Work only on the ticket assigned
   to you, on `ticket/NU-0nn-<slug>` in its own worktree. One session never
   touches two tickets.
2. **Ownership boundary.** Change only the paths listed in the ticket's Files
   field. Serialized files (IMPLEMENTATION.md section 4.4) have one open
   ticket at a time.
3. **Stop and ask** (section 4.5) when the ticket conflicts with
   ARCHITECTURE.md, needs a file outside the boundary, a dependency's output
   differs from what the ticket assumes, a check fails for an unrelated
   reason, or a tool or credential is missing. Never weaken a test, skip a
   check, or add a flag to get past a failure.
4. **No secrets.** Nothing secret in code, images, logs, fixtures, pull
   requests, or reports. `.env` is git-ignored; use `.env.example`
   placeholders and the fake model container. Never read another worktree's
   `.env`.
5. **Tests are required.** Every ticket ships the tests its Tests field lists;
   domain and use-case code is written test-first. Tests describe behavior.
6. **Layer boundaries.** `domain` → `application` → `infrastructure` / `api`
   as in IMPLEMENTATION.md section 2.3; import-linter enforces them. Modules
   talk through ports, never through another module's internals.
7. **Conventional Commits with the ticket id:** `feat(conversations): NU-026
   stream replies over SSE`. Types: feat, fix, chore, docs, test, refactor.
8. **Owner-only git identity (R-40).** Use the identity git already has.
   Never set `user.name` or `user.email`, never pass `--author`, never add
   `Co-Authored-By` or `Signed-off-by` trailers. Agents do not merge.
9. **Evidence, not opinion.** The pull request carries the headings from
   IMPLEMENTATION.md section 4.6: Ticket, Files changed, Commands run,
   Results, Acceptance criteria, Limitations, Follow-up risks, Handoff,
   Preflight. Quote command output and exit codes.
10. **No over-engineering** (section 2.8). No workers, queues, caches,
    feature-flag frameworks, generic bases, event buses, state libraries, CSS
    or component frameworks. A ticket that seems to need one stops and asks.
11. **Read only what the ticket needs.** This file, section 2 and 4 of
    IMPLEMENTATION.md, your ticket, and the sections it cites. Nothing else.
12. **Planning documents are read-only** except your ticket's Status line,
    changed on your branch with `docs: NU-0nn status <value>`.
13. **Keep the code graph current (R-41).** The post-commit hook refreshes it;
    run `make preflight` before opening or updating a pull request and after
    every rebase, and paste `graphify-out/preflight.md` into the evidence.
    Exit 1 means the graph is unhealthy; exit 2 means rebase first (branch
    behind `rebuild/v1`, baseline moved, or two Alembic heads). Parallel lanes
    open only after `make graph-overlap A=<paths> B=<paths>` says parallel.

## Code graph (R-41)

Graphify keeps an AST-only code graph of this worktree in `graphify-out/`
(git-ignored, no model call). The post-commit hook runs `make graph-update`
after every commit; `make graph-build` rebuilds from scratch (`FORCE=1` after
deleting code). Ask it before reading widely: `graphify query "<question>"`,
`graphify explain "<node>"`, `graphify path "A" "B"`, `graphify god-nodes`.
Lanes are opened only for low community overlap (`make graph-overlap`); shared
files keep one writer at a time and the graph never arbitrates; run
`make preflight` before opening or updating a pull request and again after a
rebase; its impact and conflict reports go into the evidence, while tests and
migrations alone gate a merge.

## Sessions

OpenCode project agents live in `.opencode/agents/`: `implementer` (edit and
bash allowed; one ticket in one worktree) and `reviewer` (edit and write
denied; runs `make` targets and posts the review evidence). Start a session
inside the worktree that `make worktree T=NU-0nn` created. Model ids come from
your local OpenCode configuration, never from committed files (IMPLEMENTATION.md
section 3.1). Pull requests start from `.github/pull_request_template.md`.

## Pointers

- Coding and DDD rules: IMPLEMENTATION.md section 2. Tool workflow: section 3.
- Roles, worktrees, ownership, stop-and-ask, evidence: section 4.
- Quality gates and test categories: section 5. Tickets: section 8.
- Domain model: ARCHITECTURE.md section 4. API and streaming: sections 6, 7.
- Security controls: section 17. Configuration: section 16. Layout: section 23.
