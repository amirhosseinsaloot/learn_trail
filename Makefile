# Nuroli command contract (docs/rebuild/IMPLEMENTATION.md section 2.1).
# This file holds only `help` and the per-area includes. Targets live in
# make/*.mk, one file per area, so tickets in different areas never edit
# the same file. Every target prints the commands it runs; a target whose
# tool is missing fails with a non-zero exit and a one-line reason.
SHELL := /bin/bash
.SHELLFLAGS := -e -o pipefail -c
.DEFAULT_GOAL := help

# Per-worktree runtime isolation (IMPLEMENTATION.md section 4.3): `make worktree`
# writes .worktree.env with the Compose project name, port offsets, and the
# baseline; the main checkout has no such file and uses offset 0.
-include .worktree.env
WORKTREE_VARS := COMPOSE_PROJECT_NAME NUROLI_WEB_PORT NUROLI_DEV_API_PORT NUROLI_DEV_DB_PORT NUROLI_DEV_VITE_PORT NUROLI_DEV_FAKE_MODEL_PORT BASE_COMMIT BASE_SCHEMA_HEAD
# Export only the variables the file defines; an undefined variable exported
# as an empty string would override .env inside Docker Compose.
$(foreach v,$(WORKTREE_VARS),$(if $(value $(v)),$(eval export $(v))))

.PHONY: help
help: ## List every target with its purpose
	@echo "Nuroli targets (rules and pointers in AGENTS.md):"
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-22s %s\n", $$1, $$2}'

include make/*.mk
