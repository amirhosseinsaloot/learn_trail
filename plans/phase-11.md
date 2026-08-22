# Phase 11 — Local models

Status: Complete

## Exit criterion

PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this phase:

> A chat request can be served entirely by a locally-registered LiteLLM model (Ollama/vLLM) with no outbound call to a cloud provider, and a cloud-versus-local benchmark result is recorded.

## Phase test

`tests/phases/test_phase_11.py`

## Tasks

- [x] Ollama compose service (profile-gated) + `learning-local` alias in LiteLLM (owner: `infra-devops`) — commit: `4a9c6b5`
- [x] Cloud-vs-local benchmark harness + privacy/offline mode toggle (owner: `ai-orchestration`) — commit: `4a9c6b5`

## Live results

A chat answered end to end by a local model through the gateway, no cloud call, on
this machine's GPU (llama3.2:1b, ~5s). The recorded benchmark:

    learning-fast   3074 ms   coverage 0.62   $0.0006
    learning-local  1299 ms   coverage 0.38   $0.0000

Local is faster (GPU beats the cloud round-trip) and free; the cost is answer
completeness. That is the trade privacy asks for, measured.

## Known limits, carried forward

- **The benchmark's quality metric is keyword coverage, not judgement.** It
  measures completeness and stays deterministic; it does not capture whether an
  answer reads well. A 1B local model would lose a judged contest, and dressing
  that up with a GEval score would imply a precision the four-case set does not
  have.
- **GPU is commented, not required, in the compose service.** It needs the nvidia
  container runtime, which not every host has; llama3.2:1b runs on CPU, slowly.
  The live benchmark above used a host Ollama on the GPU via
  OLLAMA_BASE_URL=http://host.docker.internal:11434/v1, which is the documented
  dev path.
- **No embedding runs local yet.** Privacy mode routes *chat* to the local model,
  but retrieval still embeds through the cloud `learning-embedding` alias, so
  "offline" is not yet total. A local embedding model is the obvious next step and
  a one-alias change.

## Not in this phase

- Advanced learning features — deferred to Phase 12
