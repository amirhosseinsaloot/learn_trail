# Infrastructure and repository-wide targets (setup, Compose stacks, audit,
# the combined check, dependency updates, backups). Owned by infra tickets.

PRE_COMMIT := uvx --from 'pre-commit>=4.6,<5' pre-commit
# gitleaks runs from its container image so no host binary is required;
# pinned by tag and digest (IMPLEMENTATION.md section 2.5).
GITLEAKS_IMAGE := ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f

define require_docker
command -v docker >/dev/null 2>&1 || { echo "make $@: docker is not installed (https://docs.docker.com/engine/install/)" >&2; exit 1; }; \
docker info >/dev/null 2>&1 || { echo "make $@: the docker daemon is not reachable" >&2; exit 1; }
endef

.PHONY: setup
setup: ## uv sync, pnpm install --frozen-lockfile, pre-commit install
	@$(require_backend_toolchain)
	@command -v pnpm >/dev/null 2>&1 || { echo "make $@: pnpm is not installed (https://pnpm.io/installation)" >&2; exit 1; }
	cd $(BACKEND_DIR) && uv sync --all-groups
	cd $(FRONTEND_DIR) && pnpm install --frozen-lockfile
	$(PRE_COMMIT) install --install-hooks

.PHONY: dev up down
dev: ## Compose dev stack: db, api with reload, Vite dev server, fake model
	@echo "make $@: not implemented until NU-010" >&2; exit 1
up: ## Release stack from compose.yaml
	@echo "make $@: not implemented until NU-010" >&2; exit 1
down: ## Stop the release stack
	@echo "make $@: not implemented until NU-010" >&2; exit 1

.PHONY: audit deps-update
audit: ## pip-audit, pnpm audit --audit-level=high, gitleaks detect
	@$(require_backend_toolchain)
	@$(require_frontend_toolchain)
	@$(require_docker)
	cd $(BACKEND_DIR) && uv export --format requirements-txt --all-groups --no-emit-project --no-hashes --quiet -o .venv/audit-requirements.txt
	cd $(BACKEND_DIR) && uvx pip-audit --requirement .venv/audit-requirements.txt --no-deps --disable-pip --strict --progress-spinner off
	cd $(FRONTEND_DIR) && pnpm audit --audit-level=high
	docker run --rm -v "$(CURDIR):/repo:ro" $(GITLEAKS_IMAGE) detect --no-git --source /repo --no-banner --redact --exit-code 1
deps-update: ## uv lock --upgrade and pnpm update --latest, then make audit check (owner only, R-40)
	@$(require_backend_toolchain)
	@$(require_frontend_toolchain)
	@echo "make deps-update: dependency updates are run and committed by the repository owner only (R-40)"
	cd $(BACKEND_DIR) && uv lock --upgrade && uv sync --all-groups
	cd $(FRONTEND_DIR) && pnpm update --latest
	$(MAKE) audit check

.PHONY: check
check: fmt-check lint typecheck test-unit test-integration test-contract test-fe migrate-check ## Local equivalent of the pull-request gate
	@echo "make check: every gate passed"

.PHONY: backup restore
backup: ## pg_dump -Fc from the db container into backups/
	@echo "make $@: not implemented until NU-041" >&2; exit 1
restore: ## Restore a dump into a stopped stack: make restore FILE=<dump>
	@echo "make $@: not implemented until NU-041" >&2; exit 1
