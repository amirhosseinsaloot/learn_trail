# Roadmap tooling track — companion to SPEC.md §15

This file maps the code-quality tooling from [CODE_QUALITY.md](CODE_QUALITY.md) onto
the §15 phases. It exists so the spec's roadmap stays untouched (edit requires
explicit approval) while each phase still names the tooling introduced alongside it.
When a phase starts, copy its tooling rows into `plans/phase-N.md` as tasks.

The rule mirrors CLAUDE.md invariant #6: a tool lands in the phase whose code it
checks — never earlier. Tier 3 tools additionally wait for their trigger condition
(see the Tier 3 table in CODE_QUALITY.md) even after their earliest phase arrives.

| Phase | Product concept (§15) | Tooling introduced alongside |
|---|---|---|
| **0** | Development environment | uv + lockfile · Ruff (lint+format, `E,F,I,B,UP,S,SIM,C4,PTH,ASYNC,RUF`) · mypy strict + Pydantic plugin · Biome · typescript-eslint (type-aware only) · `tsc --noEmit` strict · lefthook · FAST CI lane skeleton · `make` targets |
| **1** | Basic AI chat (LiteLLM, streaming, persistence) | gitleaks hook (before the first key) · anyio · respx (offline LLM tests) · testcontainers Postgres · `alembic check` · pytest-cov + diff-cover · openapi-typescript + openapi-fetch + stale-types CI check · import-linter contracts 1–4 |
| **2** | LangGraph workflow | import-linter: `ai_core.graphs` layer |
| **3** | Structured summary generation | syrupy (LearningSummary snapshots) · import-linter: `ai_core.agents` layer · trigger-watch: hypothesis (validator invariants) |
| **4** | Safety pipeline | import-linter: `ai_core.safety` sibling layer · trigger-watch: hypothesis (safety-decision properties), Semgrep custom rules (gateway + repository-layer invariants) |
| **5** | Observability | trigger-watch: deptry (framework influx by now may have bloated pyproject) |
| **6** | Evaluation-driven development | SLOW CI lane goes live: DeepEval + Promptfoo, nightly/manual, results → `evaluation_result` · trigger-watch: pytest-randomly (suite size) |
| **7** | Red teaming | Promptfoo red-team joins the SLOW lane (never hooks) |
| **8** | Search across learnings | Ragas joins the SLOW lane · import-linter: `ai_core.retrieval` sibling layer · trigger-watch: schemathesis (API surface now stable + growing) |
| **9** | Prompt optimization | no new tooling — DSPy runs inside the existing SLOW lane |
| **10** | Model routing | no new tooling — routing comparisons use the SLOW lane |
| **11** | Local models | no new tooling — local models sit behind the same gateway; respx fixtures unchanged |
| **12** | Advanced features | trigger-watch: knip + dependency-cruiser (apps/web has grown/churned by now) · pip-audit + Renovate if not already triggered |

Anytime-on-trigger (no phase owns them): pip-audit + Renovate (lockfile stable),
deptry, knip, dependency-cruiser, pytest-randomly, schemathesis, hypothesis,
Semgrep — each waits for the trigger condition in CODE_QUALITY.md's Tier 3 table.
