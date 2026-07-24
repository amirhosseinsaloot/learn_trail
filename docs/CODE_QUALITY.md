# Code quality tooling track

Status: PLANNING ONLY — nothing in this document is installed or configured yet.
Each tool lands in the phase named below, as a task in that phase's `plans/phase-N.md`,
never earlier (CLAUDE.md invariant #6 applies to tooling exactly as it applies to AI
frameworks). Per-phase mapping: [ROADMAP_TOOLING.md](ROADMAP_TOOLING.md).

Principles:

1. **One tool per job.** Every overlap is resolved in "Decisions and rejections" below.
2. **Phase-gated.** A tool is added when the code it checks exists, not before.
3. **Local-first.** Every tool runs locally with one command (proposed `make` targets
   below); CI runs the same commands, never a superset.
4. **Two CI lanes.** FAST (deterministic, free, every commit) and SLOW (model-calling
   evals, costs money, nightly/manual). No eval ever runs in a git hook.

---

## Tier 1 — Phase 0, before any AI code

| Tool | What it catches | Phase | Install |
|---|---|---|---|
| **uv** (+ committed `uv.lock`) | Unpinned/irreproducible Python envs; "works on my machine" | 0 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Ruff** — linter *and* formatter | Lint: bugs (`B`), unused/undefined (`F`), style (`E`), import order (`I`), py-upgrade (`UP`), security (`S` = flake8-bandit), simplifications (`SIM`), comprehensions (`C4`), pathlib (`PTH`), async mistakes (`ASYNC`), Ruff-native (`RUF`). Format: replaces Black + isort | 0 | `uv add --dev ruff` |
| **mypy** (strict) + Pydantic plugin | Type errors across apps/api and packages/*; plugin understands Pydantic model signatures, validators, `model_construct` | 0 | `uv add --dev mypy` (plugin ships inside `pydantic`; enabled via mypy config) |
| **Biome** | TS/JSON formatting + fast, non-type-aware lint (unused imports, correctness, a11y) in apps/web | 0 | `pnpm add -D -w @biomejs/biome` |
| **typescript-eslint** (type-aware rules ONLY) | What Biome cannot see: `no-floating-promises`, `no-misused-promises`, `await-thenable`, unsafe `any` flows — anything needing the type checker | 0 | `pnpm add -D eslint typescript-eslint` (in apps/web) |
| **tsc --noEmit** (`strict: true`, `noUncheckedIndexedAccess: true`) | Whole-program type errors; indexing into arrays/records without narrowing | 0 | ships with `pnpm add -D typescript` |
| **lefthook** | Unformatted/unlinted code reaching commits; runs staged-file checks polyglot-wide from one root config | 0 | `pnpm add -D -w lefthook` |

**The Biome / typescript-eslint split, explained:** Biome is the formatter and the fast
linter — it runs in milliseconds on staged files, so it belongs in the pre-commit hook.
But Biome has no type information. typescript-eslint is configured with *only* its
type-aware ruleset (the `recommendedTypeChecked` / `strictTypeChecked` families minus
anything Biome already covers) so the two never disagree: Biome owns style and syntax,
ESLint owns whatever requires the TypeScript type checker. ESLint therefore runs in the
FAST CI lane and pre-push, not pre-commit.

---

## Tier 2 — Phases 1–3, as the app takes shape

| Tool | What it catches | Phase | Install |
|---|---|---|---|
| **import-linter** ← priority | Architecture erosion: packages importing apps, safety importing retrieval, database importing AI code. Contracts below | 1 (initial contracts), grows in 2–3 | `uv add --dev import-linter` |
| **gitleaks** (pre-commit hook via lefthook) | Provider keys from `.env` / `infra/litellm/` leaking into commits | 1 — must land in the same task that creates the first `.env` | `brew install gitleaks` (or release binary; it's a Go binary, not a package dep) |
| **anyio** (pytest plugin) | Untested async paths; needed the moment SSE streaming lands | 1 | `uv add --dev anyio` |
| **respx** | LLM/HTTP nondeterminism and cost in tests: intercepts httpx at the transport layer, streams included | 1 | `uv add --dev respx` |
| **testcontainers-python** | SQLite-vs-Postgres behavior gaps; real Postgres per test session | 1 | `uv add --dev "testcontainers[postgres]"` |
| **`alembic check`** (CI step) | SQLAlchemy models drifting from migrations | 1 — with the first migration | no install (Alembic already present) |
| **pytest-cov + diff-cover** | Untested *changed* lines; gates on the diff, not a global % | 1 | `uv add --dev pytest-cov diff-cover` |
| **openapi-typescript + openapi-fetch** | Frontend/backend contract drift; Pydantic models become the single source of truth. CI fails when generated types are stale | 1 — with the first endpoints | `pnpm add -D openapi-typescript && pnpm add openapi-fetch` (in apps/web) |
| **syrupy** | Regressions in the `LearningSummary` structured output — snapshot the validated model dump | 3 | `uv add --dev syrupy` |

**Stale-types CI check** (part of FAST lane):

```text
1. Boot the FastAPI app, dump /openapi.json
2. pnpm --filter web openapi:gen   (openapi-typescript → src/lib/api/schema.gen.ts)
3. git diff --exit-code -- apps/web/src/lib/api/schema.gen.ts
   → non-empty diff = generated types are stale = fail
```

---

## Tier 3 — later, only when the specific pain appears

| Tool | What it does | **Trigger — reach for it when…** | Install |
|---|---|---|---|
| **schemathesis** | Fuzzes every endpoint from the OpenAPI schema | …the first bug report of an endpoint 500ing (not 422ing) on malformed input, or when the API surface stabilizes after Phase 3 | `uv add --dev schemathesis` |
| **knip** | Unused files/exports/deps in apps/web | …the first refactor that deletes a feature (e.g. summary-review UI rework) and you suspect orphaned components remain | `pnpm add -D knip` (in apps/web) |
| **deptry** | Unused/missing/transitive Python deps | …the first "import works locally, ModuleNotFoundError in CI", or after the Phase 4–5 framework influx bloats pyproject | `uv add --dev deptry` |
| **hypothesis** | Property-based tests for Pydantic validators & safety-decision logic | …Phase 3 summary validators or Phase 4 safety decisions gain nontrivial invariants ("every action ∈ {allow…block} maps to exactly one UI state") that example-based tests keep missing edge cases on | `uv add --dev hypothesis` |
| **dependency-cruiser** | TS import cycles & layering in apps/web | …the first circular-import warning in a Next.js build, or apps/web crosses ~50 modules | `pnpm add -D dependency-cruiser` |
| **pip-audit + Renovate** | Known-CVE deps; automated update PRs | …the lockfile is stable (post-Phase 1) — earlier it's churn without payoff. Renovate is a GitHub app, no install | `uv add --dev pip-audit` |
| **Semgrep OSS** (custom rules) | Codebase-specific invariants — see rules below | …the first review that catches a human/agent violating invariant #2 (direct provider call) or bypassing the repository layer. Until then, review + import-linter carry it | `uv tool install semgrep` |
| **pytest-randomly** | Hidden test-order dependencies | …the first "passes alone, fails in suite" incident, or the suite crosses ~100 tests | `uv add --dev pytest-randomly` |

**Proposed Semgrep rules** (sketches, to be refined when the trigger fires):

```yaml
rules:
  - id: model-call-bypasses-litellm-gateway
    message: >
      Model providers are only reachable through the LiteLLM gateway aliases
      (learning-fast / learning-deep / safety-judge). Direct provider SDK usage
      or hard-coded provider model strings violate CLAUDE.md invariant #2.
    severity: ERROR
    languages: [python]
    paths:
      exclude: ["packages/ai_core/models/gateway.py"]  # the one sanctioned client factory
    patterns:
      - pattern-either:
          - pattern: import anthropic
          - pattern: import openai
          - pattern-regex: 'model\s*=\s*["''](claude-|gpt-|gemini-|mistral)'

  - id: route-touches-db-outside-repository-layer
    message: >
      API routes must go through the repository layer in packages/database —
      no inline SQLAlchemy queries in route handlers.
    severity: ERROR
    languages: [python]
    paths:
      include: ["apps/api/**/routes/**"]
    patterns:
      - pattern-either:
          - pattern: from sqlalchemy import ...
          - pattern: $SESSION.execute(...)
          - pattern: select($X)
```

---

## Decisions and rejections

Either/or choices, recorded so no session re-litigates them:

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Python lint/format | **Ruff** (lint + format) | Black, isort, flake8, Bandit | Ruff's `I` rules replace isort, `ruff format` replaces Black, its rule engine replaces flake8, and the `S` rule set *is* flake8-bandit — a separate Bandit would double-report the same findings |
| Python type checker | **mypy** (strict) + Pydantic plugin | Pyright | One checker, not two arguing. mypy chosen for the first-party Pydantic plugin (this codebase is Pydantic-heavy by design — invariant #4) and the plugin ecosystem (SQLAlchemy). Spec §6 says "mypy or Pyright"; this resolves it |
| TS format + basic lint | **Biome** | ESLint-as-formatter, Prettier | Speed (pre-commit viable) and one config for format+lint |
| TS type-aware lint | **typescript-eslint, type-aware rules only** | full ESLint preset | Anything not needing type info is Biome's job; overlap = contradictory autofixes |
| Git hooks | **lefthook** | pre-commit | Polyglot monorepo: lefthook is a language-neutral Go binary driving Ruff, Biome, and gitleaks from one root file; pre-commit is Python-centric and would bolt the TS toolchain onto a Python framework |
| Async test plugin | **anyio** | pytest-asyncio | FastAPI, Starlette, and httpx are themselves built on anyio — one async abstraction end to end, no event-loop-fixture mismatch with httpx test clients |
| LLM call replay | **respx** | pytest-recording (VCR) | All model traffic is httpx under the hood (OpenAI-compatible client → LiteLLM proxy). respx intercepts at the httpx transport layer with first-class async + streaming support, which SSE tests need. VCR cassettes additionally record real request headers — an `Authorization: Bearer sk-…` sitting in a committed cassette is exactly the leak gitleaks exists to prevent; hand-built respx fixtures never contain secrets |
| Test database | **testcontainers (real Postgres)** | SQLite stand-in | pgvector arrives in Phase 8, and JSONB/full-text behavior differs today; SQLite green ≠ Postgres green |
| Coverage gate | **diff-cover (changed lines)** | total-% threshold | Total % rewards padding old code with trivial tests; changed-line coverage gates what each commit actually touched |

Rejected outright (do not add):

- **Black, isort, flake8, Bandit** — subsumed by Ruff (above).
- **Pyright** — mypy chosen (above).
- **Vulture** — dead-code detection with a false-positive rate that trains people to ignore it; Ruff `F401`/`F841` plus knip (TS side, on trigger) cover the useful subset.
- **Radon / Xenon** — complexity metrics; Ruff's `C901` (mccabe) covers the actionable part without a second report format.
- **SonarQube** — a server, a database, and a quality-gate bureaucracy for a single-user repo; every finding it would produce is covered by Ruff/mypy/Semgrep.
- **commitlint** — enforcing commit-message grammar on a single committer is process without a consumer.
- **CodeQL** — needs a public repo or GitHub Advanced Security; Semgrep OSS fills the semantic-rule niche when triggered.

---

## CI lane design

Two lanes, hard-separated. The dividing line: **does it call a model?**

### FAST lane — every commit and every PR, target < 2 minutes

Deterministic, free, no network beyond package caches and a throwaway Postgres.

| Step | Command (also the local command) | Budget |
|---|---|---|
| Python lint + format | `make lint-py` → `ruff check . && ruff format --check .` | ~5 s |
| Python types | `make type-py` → `mypy .` (incremental cache in CI) | ~30 s |
| Architecture | `make arch` → `lint-imports` | ~5 s |
| Migration drift | `make db-check` → `alembic check` (vs. throwaway Postgres service) | ~10 s |
| Unit tests | `make test` → `pytest -m "not slow"` (respx-mocked, testcontainers Postgres) | ~45 s |
| Changed-line coverage | `diff-cover coverage.xml --fail-under=90` | ~2 s |
| TS format + lint | `make lint-web` → `biome ci . && eslint .` | ~15 s |
| TS types | `make type-web` → `tsc --noEmit` | ~20 s |
| API contract | stale-types check (see Tier 2) | ~10 s |
| Secrets | `gitleaks detect` (full scan in CI; `protect --staged` in the hook) | ~3 s |

If the lane drifts past ~2 minutes, move the slowest step to pre-push instead of
pre-commit and parallelize CI jobs (py / web as separate jobs) — do not delete checks.

### SLOW lane — nightly + manual dispatch only

The §9 evaluation suite: DeepEval metrics, Promptfoo comparisons/red-team, Ragas
(Phase 8+). Calls real models through the LiteLLM gateway; costs money; scores are
nondeterministic.

- Triggers: nightly cron + manual (`workflow_dispatch` / `make evals`). Optionally
  required on PRs that touch `prompts/` — as a PR *check*, never a hook.
- **Never in a git hook.** lefthook's config will not reference this lane; a hook
  that costs money or flakes teaches people to `--no-verify`, which then bypasses
  the cheap checks too.
- Results persist to `evaluation_result` (§17) so regressions are queryable, with
  thresholds enforced per Phase 6's exit criterion.

### Git hooks (lefthook), for completeness

- **pre-commit** (< 5 s, staged files only): `ruff check --fix`, `ruff format`,
  `biome check --write`, `gitleaks protect --staged`.
- **pre-push**: `mypy`, `tsc --noEmit`, `eslint`, `pytest -m "not slow"`,
  `lint-imports`.

---

## import-linter contracts (derived from §16)

Root packages once Phase 1 code exists: `api` (apps/api), `ai_core`, `evals`,
`database` (packages/*). apps/web is TypeScript — its equivalent is dependency-cruiser,
on trigger (Tier 3).

```toml
[tool.importlinter]
root_packages = ["api", "ai_core", "evals", "database"]

# 1. Packages never import apps. The apps are consumers; a package that imports
#    an app can never be tested or reused in isolation.
[[tool.importlinter.contracts]]
name = "Packages are app-independent"
type = "forbidden"
source_modules = ["ai_core", "evals", "database"]
forbidden_modules = ["api"]

# 2. Monorepo layering: api may import anything below it; evals may import
#    ai_core (judges evaluate graphs/agents); nothing imports upward.
[[tool.importlinter.contracts]]
name = "Monorepo layers"
type = "layers"
layers = ["api", "evals", "ai_core"]

# 3. database is the bottom: pure persistence, imports no AI or eval code.
[[tool.importlinter.contracts]]
name = "Database imports nothing internal"
type = "forbidden"
source_modules = ["database"]
forbidden_modules = ["ai_core", "evals", "api"]

# 4. ai_core is persistence-free: model/graph code never imports the database
#    package. Persistence happens in api via database; the Phase 2 LangGraph
#    Postgres checkpointer is configured with a connection string, not an import.
[[tool.importlinter.contracts]]
name = "AI core is persistence-free"
type = "forbidden"
source_modules = ["ai_core"]
forbidden_modules = ["database"]

# 5. Internal layering of ai_core (§16 subpackages; prompts/ excluded — prompt
#    content lives at top-level prompts/, loaded as files, never imported).
#    Siblings on one layer are independent: safety must not import
#    retrieval, retrieval must not import safety, neither may import models'
#    siblings — the §16 boundaries stay real.
[[tool.importlinter.contracts]]
name = "ai_core internal layers"
type = "layers"
layers = [
    "ai_core.graphs",                                  # workflows (Phase 2+)
    "ai_core.agents",                                  # typed AI tasks (Phase 3+)
    "ai_core.models : ai_core.safety : ai_core.retrieval",  # independent siblings
    "ai_core.telemetry",                               # importable by all above
    "ai_core.schemas",                                 # bottom: pure Pydantic
]
```

Contracts land incrementally: 1–4 in Phase 1 (the moment `ai_core` and `database`
have code), contract 5 grows a layer per phase (graphs in 2, agents in 3, safety in 4,
retrieval in 8) — add the layer in the same task that creates the subpackage.

---

## Checklist (work through in order)

### Phase 0
- [ ] Install uv; `uv init` workspace; commit `uv.lock`
- [ ] Ruff configured with `E,F,I,B,UP,S,SIM,C4,PTH,ASYNC,RUF`; `ruff format` as the only formatter
- [ ] mypy strict + Pydantic plugin; no Pyright anywhere (incl. editor config note)
- [ ] Biome for apps/web (format + fast lint)
- [ ] typescript-eslint, type-aware rules only, zero overlap with Biome
- [ ] tsconfig: `strict: true`, `noUncheckedIndexedAccess: true`; `tsc --noEmit` wired
- [ ] lefthook root config: pre-commit (ruff/biome/gitleaks-ready), pre-push (types/tests)
- [ ] `make` targets: `lint-py`, `type-py`, `lint-web`, `type-web`, `test`, `fast`
- [ ] FAST CI lane running all of the above

### Phase 1
- [ ] gitleaks hook — **before** the first `.env` / LiteLLM key exists
- [ ] anyio test plugin; first streaming test
- [ ] respx fixtures for the LiteLLM-bound httpx traffic; `pytest` runs offline
- [ ] testcontainers Postgres session fixture
- [ ] `alembic check` in FAST lane (first migration lands this phase)
- [ ] pytest-cov + diff-cover gate on changed lines
- [ ] openapi-typescript + openapi-fetch; stale-types check in FAST lane
- [ ] import-linter contracts 1–4

### Phase 2
- [ ] import-linter: add `ai_core.graphs` layer

### Phase 3
- [ ] syrupy snapshots for validated `LearningSummary` output
- [ ] import-linter: add `ai_core.agents` layer
- [ ] (trigger watch) hypothesis, if summary validators accumulate invariants

### Phase 4+
- [ ] import-linter: add `ai_core.safety` to the sibling layer (4), `ai_core.retrieval` (8)
- [ ] SLOW lane becomes real in Phase 6 (DeepEval/Promptfoo), Ragas joins in 8
- [ ] Tier 3 tools strictly on their triggers (see table) — record each adoption
      + trigger as a line in this doc when it happens

---

## Conflicts found with the spec (flagged, not silently resolved)

1. **§6 "mypy or Pyright"** — resolved here to mypy-only (recorded above).
   `plans/phase-0.md` previously mirrored the spec's ambiguity ("mypy/Pyright");
   the plan has been aligned to mypy. The spec text itself is untouched.
2. **§6 suggests Zod for frontend validation** vs. Tier 2's openapi-typescript
   making Pydantic the single source of truth. Hand-written Zod schemas for API
   shapes would be a *second* source of truth that drifts. Proposed resolution
   (needs your call): Zod only for purely-local form state, never for API
   request/response shapes — those come from the generated types.
3. **§19 "Start with this exact subset"** lists DeepEval/Phoenix/LangGraph, which
   §15 phases in at 6/5/2. Same end-state-vs-Phase-0 ambiguity already resolved
   for docker-compose (services join compose in the phase that introduces their
   concept); this doc reads §19 the same way (end state, not
   day one). Flagging because tooling (DeepEval) is affected: the SLOW lane
   exists as *design* from Phase 0 but gets its first real job in Phase 6.
4. **"typescript-eslint type-aware rules only"** drops `eslint-config-next`
   (Next.js's own rules: `@next/next/no-img-element`, react-hooks deps, etc.),
   which Biome does not fully replace. Options: (a) accept the loss, (b) allow
   `@next/eslint-plugin-next` as the one non-type-aware exception. Needs your
   call; (b) recommended — it's domain rules, not style, so no Biome overlap.
