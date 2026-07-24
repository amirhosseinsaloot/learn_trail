"""Phase 11 — Local models

See docs/SPEC.md, "Phase 11 — Local models" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

import pytest


@pytest.mark.phase
def test_phase_11_exit_criterion():
    """Phase 11 — Local models.

    PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this
    phase. This is a derived stand-in, not a quote from the spec:

        "A chat request can be served entirely by a locally-registered LiteLLM model (Ollama/vLLM) with no outbound call to a cloud provider, and a cloud-versus-local benchmark result is recorded."

    TODO(phase 11): replace this placeholder with a real assertion for the
    criterion above once Phase 11 is implemented. Until then it must stay red.
    """
    pytest.fail("Phase 11 (Local models) not yet implemented.")
