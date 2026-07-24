SHELL := /bin/bash
.ONESHELL:

# Use the project venv when it exists so phase tests run with the project's
# pinned deps; fall back to ambient python3 before Phase 0 creates .venv.
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

# Spaces encoded as underscores so `for entry in $(PHASE_TITLES)` word-splits
# on whitespace correctly; converted back to spaces before printing.
PHASE_TITLES := \
	0:Development_environment \
	1:Basic_AI_chat \
	2:LangGraph_workflow \
	3:Structured_summary_generation \
	4:Safety_pipeline \
	5:Observability \
	6:Evaluation-driven_development \
	7:Red_teaming \
	8:Search_across_approved_learnings \
	9:Prompt_optimization \
	10:Model_routing \
	11:Local_models \
	12:Advanced_learning_features

.PHONY: status

# Single command that answers "where am I": per-phase exit-criterion test
# results, then recent git history and working-tree state. Status is derived
# by running code, never read from a markdown claim.
status:
	@echo "== LearnTrail phase status =="
	@for entry in $(PHASE_TITLES); do \
		n="$${entry%%:*}"; \
		title="$${entry#*:}"; \
		title="$${title//_/ }"; \
		f="tests/phases/test_phase_$${n}.py"; \
		if [ ! -f "$$f" ]; then \
			printf "  Phase %-2s %-32s MISSING\n" "$$n" "$$title"; \
			continue; \
		fi; \
		if $(PY) -m pytest -q "$$f" >/dev/null 2>&1; then \
			printf "  Phase %-2s %-32s PASS\n" "$$n" "$$title"; \
		else \
			printf "  Phase %-2s %-32s FAIL\n" "$$n" "$$title"; \
		fi; \
	done
	@echo
	@echo "== Recent commits =="
	@git log --oneline -5 2>&1 || echo "  (not a git repository)"
	@echo
	@echo "== Working tree =="
	@git status --short 2>&1 || true
	@if [ -z "$$(git status --short 2>/dev/null)" ]; then echo "  (clean)"; fi
