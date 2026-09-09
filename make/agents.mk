# Agent workflow targets (worktrees per ticket). Owned by the agents area.

.PHONY: worktree worktree-clean
worktree: ## Create ../nuroli-NU-0nn on branch ticket/NU-0nn-<slug>: make worktree T=NU-0nn
	@echo "make $@: not implemented until NU-005" >&2; exit 1
worktree-clean: ## Remove a ticket worktree and its Compose project: make worktree-clean T=NU-0nn
	@echo "make $@: not implemented until NU-005" >&2; exit 1
