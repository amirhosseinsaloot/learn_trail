"""Phase 7 — Red teaming

See docs/SPEC.md, "Phase 7 — Red teaming" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

import pytest


@pytest.mark.phase
def test_phase_7_exit_criterion() -> None:
    """Phase 7 — Red teaming.

    Exit criterion (verbatim, docs/SPEC.md):

        "You can measure whether a safety change improves or harms the system."

    TODO(phase 7): replace this placeholder with a real assertion for the
    criterion above once Phase 7 is implemented. Until then it must stay red.
    """
    pytest.fail("Phase 7 (Red teaming) not yet implemented.")
