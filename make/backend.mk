# Backend area targets (Python, uv, Ruff, Pyright, pytest, Alembic).
# Owned by backend tickets. Aggregate targets `fmt`, `fmt-check`, `lint`, and
# `typecheck` are declared here with their backend half; make/frontend.mk adds
# the frontend half as a second prerequisite line.

BACKEND_DIR := backend

# Fails with a one-line reason when uv is missing; installs Python 3.14 through
# uv when no interpreter satisfies backend/pyproject.toml.
define require_backend_toolchain
command -v uv >/dev/null 2>&1 || { echo "make $@: uv is not installed (https://docs.astral.sh/uv/)" >&2; exit 1; }; \
uv python find 3.14 >/dev/null 2>&1 || { echo "make $@: Python 3.14 not found; running: uv python install 3.14"; uv python install 3.14; }
endef

.PHONY: fmt fmt-check lint typecheck
fmt: fmt-backend ## Ruff format (backend) and Prettier write (frontend)
fmt-check: fmt-check-backend ## Ruff format --check and Prettier --check
lint: lint-backend ## Ruff lint, import-linter boundaries, ESLint
typecheck: typecheck-backend ## Pyright and tsc --noEmit

.PHONY: fmt-backend fmt-check-backend lint-backend typecheck-backend
fmt-backend: ## Ruff format in backend/
	@$(require_backend_toolchain)
	cd $(BACKEND_DIR) && uv run ruff format .
fmt-check-backend: ## Ruff format --check in backend/
	@$(require_backend_toolchain)
	cd $(BACKEND_DIR) && uv run ruff format --check .
lint-backend: ## Ruff check and import-linter in backend/
	@$(require_backend_toolchain)
	cd $(BACKEND_DIR) && uv run ruff check .
typecheck-backend: ## Pyright in backend/
	@$(require_backend_toolchain)
	cd $(BACKEND_DIR) && uv run pyright

.PHONY: test-unit test-integration test-contract
test-unit: ## Backend unit tests (no database, no network)
	@$(require_backend_toolchain)
	cd $(BACKEND_DIR) && uv run pytest tests/unit -q
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
