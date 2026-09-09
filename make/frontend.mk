# Frontend area targets (pnpm, Vite, ESLint, Prettier, Vitest, Playwright).
# Owned by frontend tickets. The aggregate targets are declared in
# make/backend.mk; this file adds their frontend half.

fmt: fmt-frontend
fmt-check: fmt-check-frontend
lint: lint-frontend
typecheck: typecheck-frontend

.PHONY: fmt-frontend fmt-check-frontend lint-frontend typecheck-frontend
fmt-frontend: ## Prettier --write in frontend/
	@echo "make $@: not implemented until NU-003" >&2; exit 1
fmt-check-frontend: ## Prettier --check in frontend/
	@echo "make $@: not implemented until NU-003" >&2; exit 1
lint-frontend: ## ESLint in frontend/
	@echo "make $@: not implemented until NU-003" >&2; exit 1
typecheck-frontend: ## tsc --noEmit in frontend/
	@echo "make $@: not implemented until NU-003" >&2; exit 1

.PHONY: test-fe e2e
test-fe: ## Vitest
	@echo "make $@: not implemented until NU-003" >&2; exit 1
e2e: ## Playwright against the Compose test stack with the fake model
	@echo "make $@: not implemented until NU-008" >&2; exit 1
