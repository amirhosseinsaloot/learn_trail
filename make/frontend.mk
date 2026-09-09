# Frontend area targets (pnpm, Vite, ESLint, Prettier, Vitest, Playwright).
# Owned by frontend tickets. The aggregate targets are declared in
# make/backend.mk; this file adds their frontend half.

FRONTEND_DIR := frontend

# Fails with a one-line reason when pnpm is missing or dependencies are not
# installed, instead of failing deep inside a tool.
define require_frontend_toolchain
command -v pnpm >/dev/null 2>&1 || { echo "make $@: pnpm is not installed (https://pnpm.io/installation)" >&2; exit 1; }; \
test -d $(FRONTEND_DIR)/node_modules || { echo "make $@: $(FRONTEND_DIR)/node_modules is missing; run make setup" >&2; exit 1; }
endef

fmt: fmt-frontend
fmt-check: fmt-check-frontend
lint: lint-frontend
typecheck: typecheck-frontend

.PHONY: fmt-frontend fmt-check-frontend lint-frontend typecheck-frontend
fmt-frontend: ## Prettier --write in frontend/
	@$(require_frontend_toolchain)
	cd $(FRONTEND_DIR) && pnpm exec prettier --write .
fmt-check-frontend: ## Prettier --check in frontend/
	@$(require_frontend_toolchain)
	cd $(FRONTEND_DIR) && pnpm exec prettier --check .
lint-frontend: ## ESLint in frontend/
	@$(require_frontend_toolchain)
	cd $(FRONTEND_DIR) && pnpm exec eslint .
typecheck-frontend: ## tsc --noEmit in frontend/
	@$(require_frontend_toolchain)
	cd $(FRONTEND_DIR) && pnpm exec tsc --noEmit

.PHONY: test-fe e2e
test-fe: ## Vitest
	@$(require_frontend_toolchain)
	cd $(FRONTEND_DIR) && pnpm exec vitest run
e2e: ## Playwright with axe; Vite dev server only until NU-022 adds the Compose test stack
	@$(require_frontend_toolchain)
	cd $(FRONTEND_DIR) && pnpm exec playwright install chromium
	cd $(FRONTEND_DIR) && pnpm exec playwright test
