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
	cd $(BACKEND_DIR) && uv run lint-imports
typecheck-backend: ## Pyright in backend/
	@$(require_backend_toolchain)
	cd $(BACKEND_DIR) && uv run pyright

# Host-side database access for tests and Alembic. Unless CI already provides
# NUROLI_TEST_DATABASE_URL (and NUROLI_DATABASE_URL) for its PostgreSQL service,
# this starts the dev stack's db container, reads the password from .env, and
# points both URLs at the published port of this worktree. The worktree's own
# Compose project name and ports win over the values in .env.
DEV_DB_SERVICE := db
define with_dev_db
if test -z "$${NUROLI_TEST_DATABASE_URL:-}"; then \
  $(require_docker); $(require_env_file); \
  echo "docker compose -f compose.yaml -f compose.dev.yaml up --detach --wait $(DEV_DB_SERVICE)"; \
  docker compose -f compose.yaml -f compose.dev.yaml up --detach --wait $(DEV_DB_SERVICE) >/dev/null; \
  set -a; . ./.env; set +a; \
  $(foreach v,$(WORKTREE_VARS),$(if $(value $(v)),export $(v)="$($(v))";)) \
  export NUROLI_DATABASE_URL="postgresql+asyncpg://nuroli:$$POSTGRES_PASSWORD@localhost:$${NUROLI_DEV_DB_PORT:-5432}/nuroli"; \
  export NUROLI_TEST_DATABASE_URL="postgresql+asyncpg://nuroli:$$POSTGRES_PASSWORD@localhost:$${NUROLI_DEV_DB_PORT:-5432}/nuroli_test"; \
  docker compose -f compose.yaml -f compose.dev.yaml exec -T $(DEV_DB_SERVICE) psql -U nuroli -d nuroli -tAc "SELECT 1 FROM pg_database WHERE datname = 'nuroli_test'" | grep -qx 1 \
    || docker compose -f compose.yaml -f compose.dev.yaml exec -T $(DEV_DB_SERVICE) psql -U nuroli -d nuroli -c "CREATE DATABASE nuroli_test" >/dev/null; \
fi
endef

# Creates or drops a scratch database on the same server as NUROLI_DATABASE_URL
# (used by migrate-check for the upgrade and downgrade round trip).
SCRATCH_DB := uv run --project $(CURDIR)/$(BACKEND_DIR) --quiet python $(CURDIR)/$(BACKEND_DIR)/migrations/scratch_db.py

.PHONY: test-unit test-integration test-contract
test-unit: ## Backend unit tests (no database, no network)
	@$(require_backend_toolchain)
	cd $(BACKEND_DIR) && uv run pytest tests/unit -q
test-integration: ## Backend tests against PostgreSQL from the dev stack (started if needed)
	@$(require_backend_toolchain)
	@$(with_dev_db) && echo "cd $(BACKEND_DIR) && uv run pytest tests/integration -q" && cd $(BACKEND_DIR) && uv run pytest tests/integration -q
test-contract: ## Adapter contract tests against recorded fixtures
	@echo "make $@: not implemented until NU-021" >&2; exit 1

.PHONY: migrate migration migrate-check
migrate: ## alembic upgrade head against the dev database
	@$(require_backend_toolchain)
	@$(with_dev_db) && echo "cd $(BACKEND_DIR) && uv run alembic upgrade head" && cd $(BACKEND_DIR) && uv run alembic upgrade head
migration: ## Autogenerate a migration for review: make migration name=<slug>
	@$(require_backend_toolchain)
	@test -n "$(name)" || { echo "make $@: pass name=<slug>" >&2; exit 1; }
	@$(with_dev_db) && next=$$(printf '%04d' $$(( $$(ls $(BACKEND_DIR)/migrations/versions | grep -oE '^[0-9]{4}' | sort -n | tail -1 | sed 's/^0*//') + 1 ))) \
	  && echo "cd $(BACKEND_DIR) && uv run alembic revision --autogenerate --rev-id $$next -m \"$(name)\"" \
	  && cd $(BACKEND_DIR) && uv run alembic revision --autogenerate --rev-id "$$next" -m "$(name)"
migrate-check: ## alembic check plus upgrade and downgrade round trip on an empty database
	@$(require_backend_toolchain)
	@$(with_dev_db) && scratch="nuroli_migrate_check_$$$$" \
	  && echo "creating scratch database $$scratch" && $(SCRATCH_DB) "$$NUROLI_DATABASE_URL" create "$$scratch" \
	  && export NUROLI_DATABASE_URL="$${NUROLI_DATABASE_URL%/*}/$$scratch" \
	  && trap '$(SCRATCH_DB) "$$NUROLI_DATABASE_URL" drop "$$scratch"' EXIT \
	  && cd $(BACKEND_DIR) \
	  && echo "uv run alembic upgrade head" && uv run alembic upgrade head \
	  && echo "uv run alembic check" && uv run alembic check \
	  && echo "uv run alembic downgrade base" && uv run alembic downgrade base \
	  && echo "uv run alembic upgrade head" && uv run alembic upgrade head \
	  && echo "make $@: no drift; upgrade and downgrade round trip ok"

.PHONY: check-model
check-model: ## Run `nuroli check-model` inside the API container
	@echo "make $@: not implemented until NU-021" >&2; exit 1
