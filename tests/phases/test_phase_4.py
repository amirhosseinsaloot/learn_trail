"""Phase 4 — Safety pipeline

See docs/SPEC.md, "Phase 4 — Safety pipeline" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

import pytest


@pytest.mark.phase
def test_phase_4_exit_criterion() -> None:
    """Phase 4 — Safety pipeline.

    Exit criterion (verbatim, docs/SPEC.md):

        "Every model interaction has an explicit, testable safety path."

    TODO(phase 4): replace this placeholder with a real assertion for the
    criterion above once Phase 4 is implemented. Until then it must stay red.
    """
    pytest.fail("Phase 4 (Safety pipeline) not yet implemented.")
