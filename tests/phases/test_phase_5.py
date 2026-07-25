"""Phase 5 — Observability

See docs/SPEC.md, "Phase 5 — Observability" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

import pytest


@pytest.mark.phase
def test_phase_5_exit_criterion() -> None:
    """Phase 5 — Observability.

    Exit criterion (verbatim, docs/SPEC.md):

        "A poor answer can be traced through context construction, model
        execution, guardrails and persistence."

    How this will be asserted: a chat request emits a trace containing the
    expected span names (chat.request, load_conversation, input_guardrails,
    context_builder, llm.generate, output_guardrails, persist_message) — the
    four stages the criterion names, made observable. That span list is an
    implementation choice, not the criterion itself.

    TODO(phase 5): replace this placeholder with a real assertion for the
    criterion above once Phase 5 is implemented. Until then it must stay red.
    """
    pytest.fail("Phase 5 (Observability) not yet implemented.")
