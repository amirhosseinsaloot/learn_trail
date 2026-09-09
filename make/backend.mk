# Backend area targets (Python, uv, Ruff, Pyright, pytest, Alembic).
# Owned by backend tickets. Aggregate targets `fmt`, `fmt-check`, `lint`, and
# `typecheck` are declared here with their backend half; make/frontend.mk adds
# the frontend half as a second prerequisite line.

.PHONY: fmt fmt-check lint typecheck
fmt: fmt-backend ## Ruff format (backend) and Prettier write (frontend)
fmt-check: fmt-check-backend ## Ruff format --check and Prettier --check
lint: lint-backend ## Ruff lint, import-linter boundaries, ESLint
typecheck: typecheck-backend ## Pyright and tsc --noEmit

.PHONY: fmt-backend fmt-check-backend lint-backend typecheck-backend
fmt-backend: ## Ruff format in backend/
	@echo "make $@: not implemented until NU-002" >&2; exit 1
fmt-check-backend: ## Ruff format --check in backend/
	@echo "make $@: not implemented until NU-002" >&2; exit 1
lint-backend: ## Ruff check and import-linter in backend/
	@echo "make $@: not implemented until NU-002" >&2; exit 1
typecheck-backend: ## Pyright in backend/
	@echo "make $@: not implemented until NU-002" >&2; exit 1

.PHONY: test-unit test-integration test-contract
test-unit: ## Backend unit tests (no database, no network)
	@echo "make $@: not implemented until NU-002" >&2; exit 1
test-integration: ## Backend tests against PostgreSQL from the dev stack
	@echo "make $@: not implemented until NU-011" >&2; exit 1
test-contract: ## Adapter contract tests against recorded fixtures
	@echo "make $@: not implemented until NU-021" >&2; exit 1

.PHONY: migrate migration migrate-check
migrate: ## alembic upgrade head
	@echo "make $@: not implemented until NU-011" >&2; exit 1
migration: ## Autogenerate a migration for review: make migration name=<slug>
	@echo "make $@: not implemented until NU-011" >&2; exit 1
migrate-check: ## alembic check plus upgrade and downgrade round trip on an empty database
	@echo "make $@: not implemented until NU-011" >&2; exit 1

.PHONY: check-model
check-model: ## Run `nuroli check-model` inside the API container
	@echo "make $@: not implemented until NU-021" >&2; exit 1
