# Nuroli

Self-hosted learning companion: talk with a model you configure, optionally
with web research, then review and confirm what you learned into a searchable
knowledge library you can ask questions against.

## Installation

Not available yet. The installation guide (prerequisites, `.env`,
`docker compose up -d`, first account) is written in ticket NU-039 of
[docs/rebuild/IMPLEMENTATION.md](docs/rebuild/IMPLEMENTATION.md). Until then
this repository is under rebuild on branch `rebuild/v1`.

## Development

Start with [AGENTS.md](AGENTS.md): it lists the `make` command contract and
the rules every change follows. Architecture and decisions live in
[docs/rebuild/ARCHITECTURE.md](docs/rebuild/ARCHITECTURE.md).

Host tools: `make`, `docker`, `uv`, `pnpm`, `git`. Then:

```bash
make setup      # backend and frontend dependencies, pre-commit hooks, graphify
make help       # every target
```

Each ticket gets its own worktree, branch, Compose project, and ports:
`make worktree T=NU-0nn` creates `../nuroli-NU-0nn`, and `make worktree-clean
T=NU-0nn` removes it after merge. A code graph of the worktree lives in
`graphify-out/` (git-ignored); the post-commit hook refreshes it, and
`graphify query "<question>"` answers codebase questions from it.
