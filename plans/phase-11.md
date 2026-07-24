# Phase 11 — Local models

Status: Not started

## Exit criterion

PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this phase:

> A chat request can be served entirely by a locally-registered LiteLLM model (Ollama/vLLM) with no outbound call to a cloud provider, and a cloud-versus-local benchmark result is recorded.

## Phase test

`tests/phases/test_phase_11.py`

## Tasks

- [ ] Add Ollama or vLLM as a docker-compose service, register it in LiteLLM (owner: `infra-devops`) — commit: `____`
- [ ] Cloud-vs-local benchmark harness (latency, quality) and a privacy/offline mode toggle (owner: `ai-orchestration`) — commit: `____`

## Not in this phase

- Advanced learning features — deferred to Phase 12
