# Code-graph targets wrapping the graphify CLI (R-41; IMPLEMENTATION.md
# section 3.5). Owned by the agents area. The graph is AST-only, makes no
# network calls, and lives in the git-ignored graphify-out/ of each worktree.

GRAPH_OUT := graphify-out
FORCE ?=
GRAPH_FORCE_FLAG = $(if $(filter 1,$(FORCE)),--force,)

define require_graphify
command -v graphify >/dev/null 2>&1 || { echo "make $@: graphify is not installed; run: uv tool install graphifyy (or make setup)" >&2; exit 1; }
endef

# Node count of a graph.json (0 when missing), through the Python that uv
# manages so no host interpreter is required.
define graph_node_count
uv run --no-project --python 3.14 --quiet python -c 'import json, os, sys; p = sys.argv[1]; print(len(json.load(open(p)).get("nodes", [])) if os.path.exists(p) else 0)'
endef

# graphify leaves graph.json untouched when the topology did not change, so
# built_at_commit can lag HEAD although the graph describes HEAD's tree. On a
# clean tree the stamp is corrected so preflight does not rebuild needlessly.
define graph_stamp_head
uv run --no-project --python 3.14 --quiet python -c 'import json, subprocess, sys; p = sys.argv[1]; g = json.load(open(p)); h = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(); g["built_at_commit"] = h; json.dump(g, open(p, "w"))'
endef

define graph_built_at
uv run --no-project --python 3.14 --quiet python -c 'import json, sys; print(json.load(open(sys.argv[1])).get("built_at_commit", "unknown"))'
endef

# `make setup` (make/infra.mk) gains this prerequisite without editing that file.
setup: graph-tool-install

.PHONY: graph-tool-install
graph-tool-install: ## Install the graphify CLI as a uv tool (runs inside make setup)
	uv tool install 'graphifyy>=0.9.48,<1'
	graphify --version

.PHONY: graph-build graph-update graph-watch
graph-build: ## Full code-graph rebuild into graphify-out/ (FORCE=1 after deletions)
	@$(require_graphify)
	rm -rf $(GRAPH_OUT)
	graphify update . $(GRAPH_FORCE_FLAG)
	@count=$$($(graph_node_count) $(GRAPH_OUT)/graph.json); \
	if test "$$count" -eq 0; then echo "make $@: no code files yet; wrote an empty graph"; \
	else echo "make $@: $$count nodes, built_at_commit=$$($(graph_built_at) $(GRAPH_OUT)/graph.json)"; fi
graph-update: ## Incremental graph update; refuses to shrink unless FORCE=1
	@$(require_graphify)
	@before=$$($(graph_node_count) $(GRAPH_OUT)/graph.json); \
	test ! -f $(GRAPH_OUT)/graph.json || cp $(GRAPH_OUT)/graph.json $(GRAPH_OUT)/graph.json.prev; \
	echo "graphify update . $(GRAPH_FORCE_FLAG)"; graphify update . $(GRAPH_FORCE_FLAG); \
	after=$$($(graph_node_count) $(GRAPH_OUT)/graph.json); \
	if test "$$after" -lt "$$before" && test "$(FORCE)" != "1"; then \
	  mv $(GRAPH_OUT)/graph.json.prev $(GRAPH_OUT)/graph.json; \
	  echo "make $@: refused to shrink the graph from $$before to $$after nodes (code was deleted); rerun as: make graph-update FORCE=1" >&2; exit 1; \
	fi; \
	rm -f $(GRAPH_OUT)/graph.json.prev $(GRAPH_OUT)/.needs_rebuild; \
	if test -z "$$(git status --porcelain)"; then $(graph_stamp_head) $(GRAPH_OUT)/graph.json; fi; \
	echo "make $@: $$after nodes, built_at_commit=$$($(graph_built_at) $(GRAPH_OUT)/graph.json)"
graph-watch: ## graphify watch . in the foreground
	@$(require_graphify)
	graphify watch .

# Scripts run on the backend's Python (standard library only) so no host
# interpreter is required. BASE is the integration ref the reports compare to.
GRAPH_PY := uv run --project $(BACKEND_DIR) --quiet python
# BASE is honoured only from the command line; make/agents.mk defaults its own
# BASE to the local rebuild/v1 for `make worktree`, while reports compare to origin.
GRAPH_BASE := $(if $(filter command line,$(origin BASE)),$(BASE),origin/rebuild/v1)
A ?=
B ?=

# The scripts are linted, typed, and tested with the backend toolchain;
# these prerequisites attach to the aggregate targets without editing
# make/backend.mk.
fmt: graph-scripts-fmt
fmt-check: graph-scripts-fmt-check
lint: graph-scripts-lint
typecheck: graph-scripts-typecheck
test-unit: graph-scripts-test

.PHONY: graph-scripts-fmt graph-scripts-fmt-check graph-scripts-lint graph-scripts-typecheck graph-scripts-test
graph-scripts-fmt: ## Ruff format scripts/
	cd $(BACKEND_DIR) && uv run ruff format ../scripts
graph-scripts-fmt-check: ## Ruff format --check scripts/
	cd $(BACKEND_DIR) && uv run ruff format --check ../scripts
graph-scripts-lint: ## Ruff check scripts/ with the backend rules
	cd $(BACKEND_DIR) && uv run ruff check --extend-per-file-ignores '../scripts/tests/*:S101' --extend-per-file-ignores '../scripts/tests/*:PLR2004' ../scripts
graph-scripts-typecheck: ## Pyright on scripts/ (run from scripts/ so sibling imports resolve)
	cd scripts && uv run --project ../$(BACKEND_DIR) pyright --pythonversion 3.14 .
graph-scripts-test: ## Unit tests for the graph scripts (fixture graph, temporary git repositories)
	uv run --project $(BACKEND_DIR) pytest scripts/tests -q -p no:cacheprovider

.PHONY: graph-impact graph-conflicts graph-overlap preflight
graph-impact: ## Impact report for changed files against BASE (default origin/rebuild/v1)
	$(GRAPH_PY) scripts/graph_impact.py --base $(GRAPH_BASE)
graph-conflicts: ## Overlap with every other origin/ticket/* branch
	$(GRAPH_PY) scripts/graph_conflicts.py --base $(GRAPH_BASE)
graph-overlap: ## Community overlap between two ownership boundaries: make graph-overlap A=<paths> B=<paths>
	@test -n "$(A)" && test -n "$(B)" || { echo "make $@: pass both A=<paths> and B=<paths>" >&2; exit 1; }
	$(GRAPH_PY) scripts/graph_conflicts.py --paths-a "$(A)" --paths-b "$(B)"
preflight: ## Rebase check, baseline check, graph refresh, impact and conflict reports
	@test -z "$$(git status --porcelain)" || { echo "make $@: the working tree is not clean; commit or discard changes so built_at_commit is meaningful" >&2; exit 2; }
	@git fetch --quiet origin rebuild/v1 2>/dev/null || echo "make $@: could not fetch origin/rebuild/v1; comparing against the last fetched ref" >&2
	@git rev-parse --verify --quiet "$(GRAPH_BASE)^{commit}" >/dev/null || { echo "make $@: base ref $(GRAPH_BASE) does not exist" >&2; exit 1; }
	@if test -f $(GRAPH_OUT)/.needs_rebuild || test "$$($(graph_built_at) $(GRAPH_OUT)/graph.json 2>/dev/null || echo none)" != "$$(git rev-parse HEAD)"; then \
	  echo "make $@: graph is missing, stale, or marked for rebuild; running make graph-build"; $(MAKE) graph-build; \
	else $(MAKE) graph-update; fi
	@test "$$($(graph_built_at) $(GRAPH_OUT)/graph.json)" = "$$(git rev-parse HEAD)" || { echo "make $@: graph built_at_commit still differs from HEAD after a rebuild" >&2; exit 1; }
	$(GRAPH_PY) scripts/graph_impact.py --base $(GRAPH_BASE) --strict-baseline --require-current-graph
	$(GRAPH_PY) scripts/graph_conflicts.py --base $(GRAPH_BASE)
	@{ echo "# Preflight: $$(git rev-parse --abbrev-ref HEAD) @ $$(git rev-parse --short HEAD)"; echo; echo "- working tree: clean"; echo "- graph built_at_commit: $$(git rev-parse HEAD)"; echo; cat $(GRAPH_OUT)/conflicts.md; } > $(GRAPH_OUT)/preflight.md
	@echo "make $@: ok; report written to $(GRAPH_OUT)/preflight.md"
