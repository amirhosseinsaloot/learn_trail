"""Phase 0 — Development environment

See docs/SPEC.md, "Phase 0 — Development environment" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

import pytest


@pytest.mark.phase
def test_phase_0_exit_criterion():
    """Phase 0 — Development environment.

    PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this
    phase. This is a derived stand-in, not a quote from the spec:

        "Every service docker-compose.yml defines in Phase 0 (Postgres, backend,
        frontend) reports a healthy status."

    Phoenix and LiteLLM Proxy are deliberately excluded: a service joins
    docker-compose.yml in the phase that introduces its concept (LiteLLM in
    Phase 1, Phoenix in Phase 5), and each phase test checks only the services
    that exist by its phase.

    TODO(phase 0): replace this placeholder with a real assertion for the
    criterion above once Phase 0 is implemented. Until then it must stay red.
    The real test must distinguish "environment not running" from "phase not
    built": validate `docker compose config` statically, and fail with an
    explicit "docker not running" message when the daemon is unreachable.
    """
    pytest.fail("Phase 0 (Development environment) not yet implemented.")
