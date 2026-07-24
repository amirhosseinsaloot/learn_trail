"""Phase 5 — Observability

See docs/SPEC.md, "Phase 5 — Observability" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

import pytest


@pytest.mark.phase
def test_phase_5_exit_criterion():
    """Phase 5 — Observability.

    PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this
    phase. This is a derived stand-in, not a quote from the spec:

        "A chat request emits a trace containing the expected span names (chat.request, load_conversation, input_guardrails, context_builder, llm.generate, output_guardrails, persist_message)."

    TODO(phase 5): replace this placeholder with a real assertion for the
    criterion above once Phase 5 is implemented. Until then it must stay red.
    """
    pytest.fail("Phase 5 (Observability) not yet implemented.")
