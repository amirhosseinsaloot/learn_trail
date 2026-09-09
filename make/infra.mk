# Infrastructure and repository-wide targets (setup, Compose stacks, audit,
# the combined check, dependency updates, backups). Owned by infra tickets.

.PHONY: setup
setup: ## uv sync, pnpm install --frozen-lockfile, pre-commit install
	@echo "make $@: not implemented until NU-004" >&2; exit 1

.PHONY: dev up down
dev: ## Compose dev stack: db, api with reload, Vite dev server, fake model
	@echo "make $@: not implemented until NU-010" >&2; exit 1
up: ## Release stack from compose.yaml
	@echo "make $@: not implemented until NU-010" >&2; exit 1
down: ## Stop the release stack
	@echo "make $@: not implemented until NU-010" >&2; exit 1

.PHONY: audit deps-update
audit: ## pip-audit, pnpm audit --audit-level=high, gitleaks detect
	@echo "make $@: not implemented until NU-004" >&2; exit 1
deps-update: ## uv lock --upgrade and pnpm update --latest, then make audit check (owner only, R-40)
	@echo "make $@: not implemented until NU-004" >&2; exit 1

.PHONY: check
check: fmt-check lint typecheck test-unit test-integration test-contract test-fe migrate-check ## Local equivalent of the pull-request gate
	@echo "make check: every gate passed"

.PHONY: backup restore
backup: ## pg_dump -Fc from the db container into backups/
	@echo "make $@: not implemented until NU-041" >&2; exit 1
restore: ## Restore a dump into a stopped stack: make restore FILE=<dump>
	@echo "make $@: not implemented until NU-041" >&2; exit 1
