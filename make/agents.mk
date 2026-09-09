# Agent workflow targets (IMPLEMENTATION.md section 4.3): one worktree, one
# branch, one Compose project, and one set of ports per ticket. Owned by the
# agents area.

# make worktree T=NU-0nn [S=<slug>] [BASE=<ref>]
#   T     ticket id; the numeric part n derives the port offsets
#   S     branch slug; default derived from the ticket title in IMPLEMENTATION.md
#   BASE  ref the branch starts from (default rebuild/v1; use a ticket branch
#         when the dependency is reviewed but not yet merged)
T ?=
S ?=
BASE ?= rebuild/v1
WORKTREE_PARENT := $(abspath $(CURDIR)/..)
WORKTREE_DIR = $(WORKTREE_PARENT)/nuroli-$(T)
TICKET_NUMBER = $(shell echo "$(T)" | sed -E 's/^NU-0*//')
TICKET_TITLE = $(shell grep -m1 -E '^\#\#\#\# $(T) ' docs/rebuild/IMPLEMENTATION.md | sed -E 's/^\#\#\#\# $(T) //')
# First six words of the ticket title; `scratch` when the ticket has no title yet.
DEFAULT_SLUG = $(or $(shell echo "$(TICKET_TITLE)" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$$//' | cut -d- -f1-6),scratch)
SLUG = $(if $(S),$(S),$(DEFAULT_SLUG))
TICKET_BRANCH = ticket/$(T)-$(SLUG)

define require_ticket_id
echo "$(T)" | grep -Eq '^NU-[0-9]{3}$$' || { echo "make $@: T must look like NU-0nn (got '$(T)')" >&2; exit 1; }
endef

.PHONY: worktree worktree-clean
worktree: ## Create ../nuroli-NU-0nn on branch ticket/NU-0nn-<slug>: make worktree T=NU-0nn
	@$(require_ticket_id)
	@echo "$(TICKET_BRANCH)" | grep -Eq '^ticket/NU-[0-9]{3}-[a-z0-9-]+$$' || { echo "make $@: branch name '$(TICKET_BRANCH)' does not match ^ticket/NU-[0-9]{3}-[a-z0-9-]+$$ (pass S=<slug>)" >&2; exit 1; }
	@test -z "$$(git status --porcelain --untracked-files=no)" || { echo "make $@: commit or discard your changes first; the worktree baseline must come from a clean checkout" >&2; exit 1; }
	@git rev-parse --verify --quiet "$(BASE)^{commit}" >/dev/null || { echo "make $@: base ref '$(BASE)' does not exist" >&2; exit 1; }
	@test ! -e "$(WORKTREE_DIR)" || { echo "make $@: $(WORKTREE_DIR) already exists; run 'make worktree-clean T=$(T)' first or choose another ticket" >&2; exit 1; }
	@! git show-ref --verify --quiet "refs/heads/$(TICKET_BRANCH)" || { echo "make $@: branch $(TICKET_BRANCH) already exists; delete it with 'git branch -D $(TICKET_BRANCH)' or check it out with 'git worktree add $(WORKTREE_DIR) $(TICKET_BRANCH)'" >&2; exit 1; }
	git worktree add -b "$(TICKET_BRANCH)" "$(WORKTREE_DIR)" "$(BASE)"
	@if test -f .env; then echo "cp .env $(WORKTREE_DIR)/.env"; cp .env "$(WORKTREE_DIR)/.env"; else echo "cp .env.example $(WORKTREE_DIR)/.env"; cp .env.example "$(WORKTREE_DIR)/.env"; fi
	@base_commit=$$(git rev-parse "$(BASE)^{commit}"); \
	files=$$(git ls-tree -r --name-only "$$base_commit" -- backend/migrations/versions 2>/dev/null | { grep -E '\.py$$' || true; }); \
	schema_head=none; \
	if test -n "$$files"; then \
	  src=$$(for f in $$files; do git show "$$base_commit:$$f"; done); \
	  revs=$$(echo "$$src" | { grep -E '^revision(: str)? = ' || true; } | sed -E "s/.*= *['\"]([^'\"]+)['\"].*/\1/"); \
	  downs=$$(echo "$$src" | { grep -E '^down_revision' || true; } | sed -E "s/.*= *['\"]([^'\"]+)['\"].*/\1/"); \
	  for r in $$revs; do echo "$$downs" | grep -qx "$$r" || schema_head="$$r"; done; \
	fi; \
	n=$(TICKET_NUMBER); \
	printf '%s\n' \
	  "# Written by make worktree for $(T); git-ignored. Loaded by the root Makefile." \
	  "COMPOSE_PROJECT_NAME=nuroli-nu$$(printf '%03d' $$n)" \
	  "NUROLI_WEB_PORT=$$((8080 + n))" \
	  "NUROLI_DEV_API_PORT=$$((8000 + n))" \
	  "NUROLI_DEV_DB_PORT=$$((5432 + n))" \
	  "NUROLI_DEV_VITE_PORT=$$((5173 + n))" \
	  "NUROLI_DEV_FAKE_MODEL_PORT=$$((9000 + n))" \
	  "BASE_COMMIT=$$base_commit" \
	  "BASE_SCHEMA_HEAD=$$schema_head" \
	  > "$(WORKTREE_DIR)/.worktree.env"; \
	echo "wrote $(WORKTREE_DIR)/.worktree.env:"; cat "$(WORKTREE_DIR)/.worktree.env"
	@echo "make $@: worktree ready at $(WORKTREE_DIR) on $(TICKET_BRANCH); next: cd $(WORKTREE_DIR) && make setup"

worktree-clean: ## Remove a ticket worktree and its Compose project: make worktree-clean T=NU-0nn
	@$(require_ticket_id)
	@test -d "$(WORKTREE_DIR)" || { echo "make $@: $(WORKTREE_DIR) does not exist" >&2; exit 1; }
	@if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
	  project="nuroli-nu$$(printf '%03d' $(TICKET_NUMBER))"; \
	  echo "docker compose -p $$project down --remove-orphans --volumes"; \
	  docker compose -p "$$project" down --remove-orphans --volumes; \
	else echo "make $@: docker unavailable; skipping Compose project removal for $(T)" >&2; fi
	@branch=$$(git -C "$(WORKTREE_DIR)" rev-parse --abbrev-ref HEAD); \
	if test -n "$$(git -C "$(WORKTREE_DIR)" status --porcelain)" && test "$(FORCE)" != "1"; then echo "make $@: $(WORKTREE_DIR) has uncommitted changes; commit them or rerun with FORCE=1" >&2; exit 1; fi; \
	echo "git worktree remove $(WORKTREE_DIR)"; git worktree remove $(if $(filter 1,$(FORCE)),--force,) "$(WORKTREE_DIR)"; \
	if git branch -d "$$branch" >/dev/null 2>&1; then echo "deleted merged branch $$branch"; else echo "kept branch $$branch (not merged into the current branch); delete it with: git branch -D $$branch"; fi
