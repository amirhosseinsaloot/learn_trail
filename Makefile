# Nuroli command contract (docs/rebuild/IMPLEMENTATION.md section 2.1).
# This file holds only `help` and the per-area includes. Targets live in
# make/*.mk, one file per area, so tickets in different areas never edit
# the same file. Every target prints the commands it runs; a target whose
# tool is missing fails with a non-zero exit and a one-line reason.
SHELL := /bin/bash
.SHELLFLAGS := -e -o pipefail -c
.DEFAULT_GOAL := help

.PHONY: help
help: ## List every target with its purpose
	@echo "Nuroli targets (rules and pointers in AGENTS.md):"
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-22s %s\n", $$1, $$2}'

include make/*.mk
