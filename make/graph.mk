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
	echo "make $@: $$after nodes, built_at_commit=$$($(graph_built_at) $(GRAPH_OUT)/graph.json)"
graph-watch: ## graphify watch . in the foreground
	@$(require_graphify)
	graphify watch .

.PHONY: graph-impact graph-conflicts graph-overlap preflight
graph-impact: ## Impact report for changed files against BASE (default origin/rebuild/v1)
	@echo "make $@: not implemented until NU-050" >&2; exit 1
graph-conflicts: ## Overlap with every other origin/ticket/* branch
	@echo "make $@: not implemented until NU-050" >&2; exit 1
graph-overlap: ## Community overlap between two ownership boundaries: make graph-overlap A=<paths> B=<paths>
	@echo "make $@: not implemented until NU-050" >&2; exit 1
preflight: ## Rebase check, baseline check, graph refresh, impact and conflict reports
	@echo "make $@: not implemented until NU-050" >&2; exit 1
