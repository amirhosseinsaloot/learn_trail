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

## Where am I?

```bash
make status
```

Runs the per-phase exit-criterion tests in [tests/phases/](tests/phases/) (using
`.venv/bin/python` when present) and prints git state. Status is derived by
running code, never read from a markdown claim.
