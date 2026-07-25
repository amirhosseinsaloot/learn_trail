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

.PHONY: status help lint-py type-py lint-web type-web test fast hooks

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

# Prerequisite list, not a recipe: make runs them in order and stops at the
# first failure. Cheapest and most frequently-broken checks first.
fast: lint-py type-py test lint-web type-web ## Every Phase 0 check, in one command
	@echo
	@echo "FAST lane green: lint-py, type-py, test, lint-web, type-web."

hooks: ## (Re)install the git hooks defined in lefthook.yml
	$(LEFTHOOK) install

help: ## List available targets
	@echo "LearnTrail make targets:"
	@echo
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'
