"""Phase 10 — Model routing

See docs/SPEC.md, "Phase 10 — Model routing" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

import pytest


@pytest.mark.phase
def test_phase_10_exit_criterion() -> None:
    """Phase 10 — Model routing.

    PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this
    phase. This is a derived stand-in, not a quote from the spec:

        "A request through the difficulty classifier is routed to the cheap-model
        path for a simple question and the strong-model path for a difficult one,
        and a forced timeout triggers the documented fallback strategy."

    TODO(phase 10): replace this placeholder with a real assertion for the
    criterion above once Phase 10 is implemented. Until then it must stay red.
    """
    pytest.fail("Phase 10 (Model routing) not yet implemented.")
