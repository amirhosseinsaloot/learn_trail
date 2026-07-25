"""Phase 2 — LangGraph workflow

See docs/SPEC.md, "Phase 2 — LangGraph workflow" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

import pytest


@pytest.mark.phase
def test_phase_2_exit_criterion() -> None:
    """Phase 2 — LangGraph workflow.

    Exit criterion (verbatim, docs/SPEC.md):

        "Each chat request is visible as a deterministic graph execution."

    TODO(phase 2): replace this placeholder with a real assertion for the
    criterion above once Phase 2 is implemented. Until then it must stay red.
    """
    pytest.fail("Phase 2 (LangGraph workflow) not yet implemented.")
