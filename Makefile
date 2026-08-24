SHELL := /bin/bash
.ONESHELL:

# Every check in this file is a local command first and a CI command second —
# CI runs these targets, never a superset (docs/CODE_QUALITY.md, principle 3).
# The same targets back the pre-push git hook (lefthook.yml), so a hook can
# never drift from what a human runs by hand.
#
# Phase 0 covers the FAST-lane rows whose tools exist today. Deliberately absent
# until their phase: `arch` (import-linter), `db-check` (alembic check),
# changed-line coverage (diff-cover), the stale-types check and `gitleaks
# detect` — all Tier 2 / Phase 1 — and `evals` (SLOW lane, Phase 6).

# No .DEFAULT_GOAL: `status` is the first target in the file and stays what a
# bare `make` runs, exactly as before these targets were added.

# Use the project venv when it exists so phase tests run with the project's
# pinned deps; fall back to ambient python3 before Phase 0 creates .venv.
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

# Same rule for the standalone Python tools: prefer the project venv that
# `uv sync --all-groups` creates, fall back to whatever is on PATH.
RUFF := $(shell [ -x .venv/bin/ruff ] && echo .venv/bin/ruff || echo ruff)
MYPY := $(shell [ -x .venv/bin/mypy ] && echo .venv/bin/mypy || echo mypy)

# Node-side tooling always goes through pnpm's root scripts (see package.json),
# so the exact invocations live in one place. Biome resolves only from the root
# node_modules/.bin; ESLint and tsc go through `pnpm --filter web`.
PNPM := pnpm

# lefthook is a workspace-root devDependency; prefer it over any global copy.
LEFTHOOK := $(shell [ -x node_modules/.bin/lefthook ] && echo node_modules/.bin/lefthook || echo lefthook)

# Spaces encoded as underscores so `for entry in $(PHASE_TITLES)` word-splits
# on whitespace correctly; converted back to spaces before printing.
PHASE_TITLES := \
	0:Development_environment \
	1:Basic_AI_chat \
	2:LangGraph_workflow \
	3:Structured_summary_generation \
	4:Safety_pipeline \
	5:Observability \
	6:Evaluation-driven_development \
	7:Red_teaming \
	8:Search_across_approved_learnings \
	9:Prompt_optimization \
	10:Model_routing \
	11:Local_models \
	12:Advanced_learning_features

# Docker Compose is invoked through a variable so the plugin form used here
# (`docker compose`, v2+) is stated once rather than in five recipes.
COMPOSE := docker compose

.PHONY: status help lint-py type-py lint-web type-web test fast hooks graphify-update up down logs ps

# Single command that answers "where am I": per-phase exit-criterion test
# results, then recent git history and working-tree state. Status is derived
# by running code, never read from a markdown claim.
status: ## Per-phase exit-criterion results + git state (the source of truth)
	@echo "== LearnTrail phase status =="
	@for entry in $(PHASE_TITLES); do \
		n="$${entry%%:*}"; \
		title="$${entry#*:}"; \
		title="$${title//_/ }"; \
		f="tests/phases/test_phase_$${n}.py"; \
		if [ ! -f "$$f" ]; then \
			printf "  Phase %-2s %-32s MISSING\n" "$$n" "$$title"; \
			continue; \
		fi; \
		if $(PY) -m pytest -q "$$f" >/dev/null 2>&1; then \
			printf "  Phase %-2s %-32s PASS\n" "$$n" "$$title"; \
		else \
			printf "  Phase %-2s %-32s FAIL\n" "$$n" "$$title"; \
		fi; \
	done
	@echo
	@echo "== Recent commits =="
	@git log --oneline -5 2>&1 || echo "  (not a git repository)"
	@echo
	@echo "== Working tree =="
	@git status --short 2>&1 || true
	@if [ -z "$$(git status --short 2>/dev/null)" ]; then echo "  (clean)"; fi

# ---------------------------------------------------------------------------
# FAST lane (docs/CODE_QUALITY.md). Commands are verbatim from that document's
# lane table wherever the tool exists in Phase 0.
#
# Every recipe below chains with `&&` rather than one command per line: this
# Makefile sets .ONESHELL, so a recipe's exit status would otherwise be that of
# its LAST line and an earlier failure would pass silently.
# ---------------------------------------------------------------------------

lint-py: ## Ruff: lint + formatting check, no writes (`ruff check . && ruff format --check .`)
	$(RUFF) check . && $(RUFF) format --check .

type-py: ## mypy strict over the whole Python monorepo (`mypy .`)
	$(MYPY) .

lint-web: ## Biome (ci mode) + type-aware ESLint over apps/web
	$(PNPM) run lint:web

type-web: ## TypeScript: `next typegen && tsc --noEmit` (bare tsc fails on a clean checkout)
	$(PNPM) run type:web

# `not phase` is not an optimisation, it is the contract: tests/phases/*.py are
# executable exit criteria that are RED until their phase is built (12 of 13 are
# red right now, by design). They are reported by `make status`, one phase at a
# time; folding them into the unit-test lane would make it permanently red and
# therefore ignored. `not slow` is carried from the lane table for the Phase 1+
# tests that will earn the marker.
test: ## Unit tests, excluding phase exit-criterion tests (`pytest -m "not slow and not phase"`)
	$(PY) -m pytest -m "not slow and not phase"

# --------------------------------------------------------------------------
# SLOW lane (Phase 6, docs/CODE_QUALITY.md "CI lane design").
#
# These call real models and cost real money. They are NOT in `fast`, NOT in a
# git hook, and NOT in `make status` — a paid, nondeterministic check on a path
# a developer walks fifty times a day is one they learn to bypass.
#
# Two environment problems this recipe exists to solve, both found by running the
# suite the naive way:
#
# 1. LITELLM_BASE_URL defaults to `http://litellm:4000` — the compose service
#    name, which resolves inside the network and not on the host. Without the
#    override the safety rails fail *open* (Phase 4's deliberate choice) and every
#    blocking case reports as a safety regression rather than as an unreachable
#    gateway. `InconclusiveRun` now catches that loudly rather than scoring it.
#
# 2. LITELLM_MASTER_KEY lives in the gitignored `.env`, which the compose
#    services read and a host shell does not. Without it the proxy rejects the
#    call with `[400] No connected db` — it treats the fallback placeholder as a
#    virtual key and goes looking for a database to validate it against.
#
# `.env` is sourced rather than duplicated, so there is still exactly one place
# the key lives (CLAUDE.md invariant #3). `-` on the include: a clean clone with
# no .env still parses this file and fails at the call, which is the correct
# blast radius.
# --------------------------------------------------------------------------
.PHONY: evals evals-gate evals-sync

# DEEPEVAL_TELEMETRY_OPT_OUT: DeepEval reports usage to its vendor by default.
# This repo sends prompts and answers to exactly one place on purpose (the
# LiteLLM gateway), and a second, undeclared egress from the tool that reads
# every golden case is not something to leave on by accident.
evals: export DEEPEVAL_TELEMETRY_OPT_OUT = YES
evals: ## Run the evaluation suite against real models and record the gate manifest
	uv sync --all-groups --extra judges
	set -a; [ -f .env ] && . ./.env; set +a; \
		LITELLM_BASE_URL=$${LITELLM_BASE_URL:-http://localhost:4000} $(PY) -m evals run

evals-gate: ## Free, offline: is the current prompt/model config covered by a recorded run?
	$(PY) -m evals gate

# --------------------------------------------------------------------------
# Red teaming (Phase 7). Also SLOW lane — one judge call per case, and one
# generation for the output-stage cases.
#
# `redteam` measures and compares; it exits non-zero on HARMED *and* on MIXED. A
# trade needs a human to say it was the one they meant, which is what `accept`
# is for. Silently passing a mixed verdict would let a change that stopped more
# attacks by refusing more ordinary questions merge on a green tick.
# --------------------------------------------------------------------------
.PHONY: redteam redteam-accept redteam-gate evals-retrieval optimize benchmark

redteam: ## Measure the safety posture and compare it against the recorded baseline
	set -a; [ -f .env ] && . ./.env; set +a; \
		LITELLM_BASE_URL=$${LITELLM_BASE_URL:-http://localhost:4000} $(PY) -m evals redteam run

redteam-accept: ## Measure, then promote the result to be the new baseline
	set -a; [ -f .env ] && . ./.env; set +a; \
		LITELLM_BASE_URL=$${LITELLM_BASE_URL:-http://localhost:4000} $(PY) -m evals redteam accept

# Retrieval evaluation (Phase 8). Needs the stack up: there must be a library to
# retrieve from, and each metric is a judge call.
# Prompt optimization (Phase 9). Optimizes on the train split only and compares
# on held-out — the criterion is that the gain survives data the optimizer never
# saw. Costs breadth x depth x |train| generations plus the two comparisons.
optimize: ## Optimize the summary instruction and compare on held-out examples
	uv sync --all-groups --extra optimize
	set -a; [ -f .env ] && . ./.env; set +a; \
		LITELLM_BASE_URL=$${LITELLM_BASE_URL:-http://localhost:4000} $(PY) -m evals optimize

# Cloud-vs-local benchmark (Phase 11). Needs the gateway up and, for the local
# side, an Ollama serving the model behind the `learning-local` alias — either the
# `ollama` compose profile or a host Ollama with OLLAMA_BASE_URL pointed at it.
# Records packages/evals/reports/benchmark.json; the cloud side stands even when
# local is unreachable.
benchmark: ## Cloud-vs-local latency/quality/cost benchmark
	set -a; [ -f .env ] && . ./.env; set +a; \
		LITELLM_BASE_URL=$${LITELLM_BASE_URL:-http://localhost:4000} $(PY) -m evals benchmark

evals-retrieval: ## Score retrieval precision, recall and faithfulness
	set -a; [ -f .env ] && . ./.env; set +a; \
		LITELLM_BASE_URL=$${LITELLM_BASE_URL:-http://localhost:4000} \
		DATABASE_URL=$${DATABASE_URL:-postgresql+psycopg://learntrail:learntrail@localhost:5432/learntrail} \
		$(PY) -m evals retrieval

redteam-gate: ## Free, offline: does the baseline describe the current safety config?
	$(PY) -m evals redteam-gate

evals-sync: ## Register the golden dataset cases in the database
	$(PY) -m evals sync

# Prerequisite list, not a recipe: make runs them in order and stops at the
# first failure. Cheapest and most frequently-broken checks first.
fast: lint-py type-py test lint-web type-web ## Every Phase 0 check, in one command
	@echo
	@echo "FAST lane green: lint-py, type-py, test, lint-web, type-web."

hooks: ## (Re)install the git hooks defined in lefthook.yml
	$(LEFTHOOK) install

# Graphify (dev/Claude tooling, not part of the AI application — see CLAUDE.md's
# "## graphify" section and docs/STATE.md). AST-only: no LLM call, no API cost.
graphify-update: ## Re-extract changed code and refresh the graphify knowledge graph
	graphify update .

# ---------------------------------------------------------------------------
# Local development stack (docker-compose.yml, docs/SPEC.md §6).
#
# Phase 0 is three services: postgres, backend, frontend. See the header of
# docker-compose.yml for which service joins in which later phase.
# ---------------------------------------------------------------------------

# `--wait` is the point of this target: it blocks until every service with a
# healthcheck reports healthy (or the timeout trips) and exits non-zero
# otherwise. That makes `make up` a check, not just a launch — and it is the
# same condition tests/phases/test_phase_0.py asserts. `next dev` compiles the
# first route on demand, so the frontend's probe can legitimately take a minute.
up: ## Start the local stack and block until every service is healthy
	$(COMPOSE) up -d --wait --wait-timeout 300

# No -v: the postgres_data volume survives, so a restart does not silently
# discard the database. Throwing the data away is the explicit
# `docker compose down -v`.
down: ## Stop the local stack, keeping the Postgres volume
	$(COMPOSE) down

logs: ## Follow logs from every service in the local stack
	$(COMPOSE) logs --follow

ps: ## Show each service's container state and health
	$(COMPOSE) ps

help: ## List available targets
	@echo "LearnTrail make targets:"
	@echo
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'
