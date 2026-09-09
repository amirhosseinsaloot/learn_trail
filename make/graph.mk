# Code-graph targets wrapping the graphify CLI (R-41). Owned by the agents area.

.PHONY: graph-build graph-update graph-watch
graph-build: ## Full code-graph rebuild into graphify-out/ (FORCE=1 after deletions)
	@echo "make $@: not implemented until NU-049" >&2; exit 1
graph-update: ## Incremental graph update; refuses to shrink unless FORCE=1
	@echo "make $@: not implemented until NU-049" >&2; exit 1
graph-watch: ## graphify watch . in the foreground
	@echo "make $@: not implemented until NU-049" >&2; exit 1

.PHONY: graph-impact graph-conflicts graph-overlap preflight
graph-impact: ## Impact report for changed files against BASE (default origin/rebuild/v1)
	@echo "make $@: not implemented until NU-050" >&2; exit 1
graph-conflicts: ## Overlap with every other origin/ticket/* branch
	@echo "make $@: not implemented until NU-050" >&2; exit 1
graph-overlap: ## Community overlap between two ownership boundaries: make graph-overlap A=<paths> B=<paths>
	@echo "make $@: not implemented until NU-050" >&2; exit 1
preflight: ## Rebase check, baseline check, graph refresh, impact and conflict reports
	@echo "make $@: not implemented until NU-050" >&2; exit 1
