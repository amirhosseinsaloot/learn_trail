# LearnTrail

Single-user AI learning workspace: persistent Q&A conversations distilled into
human-approved "Learnings." Full spec: [docs/SPEC.md](docs/SPEC.md); agent rules:
[CLAUDE.md](CLAUDE.md).

## Python environment

Managed by [uv](https://docs.astral.sh/uv/). Install uv once:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, from the repo root, one command creates `.venv/`, fetches the pinned
Python 3.12 interpreter, and installs every dev tool from the committed
`uv.lock`:

```bash
uv sync --all-groups
```

Tools land in `.venv/bin/` (`pytest`, `ruff`, `mypy`). Run them via
`uv run <tool>` or the `.venv/bin/` path — no `activate` required.
`uv.lock` is committed and is the source of truth for versions; change
dependencies with `uv add`/`uv remove`, never by editing `.venv/` in place.

## Checks and git hooks

Every check runs locally with one command, and CI runs the same targets rather
than a superset (docs/CODE_QUALITY.md):

```bash
make fast     # every Phase 0 check: lint-py, type-py, test, lint-web, type-web
make help     # the full target list
```

Git hooks are managed by [lefthook](https://lefthook.dev) from the root
`lefthook.yml`: **pre-commit** autofixes staged files (Ruff lint + format,
Biome) in well under a second, **pre-push** runs mypy, `tsc --noEmit`, ESLint
and the unit tests. `pnpm install` wires them automatically; after an install
that skipped build scripts, run:

```bash
make hooks    # = lefthook install
```

`make test` deliberately excludes the `tests/phases/` exit-criterion tests
(`-m "not phase"`): those are red until their phase is built and are reported
one phase at a time by `make status`.

## Where am I?

```bash
make status
```

Runs the per-phase exit-criterion tests in [tests/phases/](tests/phases/) (using
`.venv/bin/python` when present) and prints git state. Status is derived by
running code, never read from a markdown claim.

## Claude Code tooling (optional)

[graphify](https://github.com/jarkius-ai/graphify) builds a knowledge graph of
this repo (`graphify-out/graph.json`, `GRAPH_REPORT.md`) that Claude Code uses to
navigate the codebase — see [CLAUDE.md](CLAUDE.md)'s `## graphify` section for the
rules it follows. Installed as isolated dev tooling (`uv tool install graphifyy`),
not a `pyproject.toml` dependency. After changing code, refresh the graph:

```bash
make graphify-update
```
