"""Phase 5 — Observability

See docs/SPEC.md, "Phase 5 — Observability" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytestmark = pytest.mark.phase


@pytest.mark.phase
def test_phase_5_exit_criterion() -> None:
    """Phase 5 — Observability.

    Exit criterion (verbatim, docs/SPEC.md):

        "A poor answer can be traced through context construction, model
        execution, guardrails and persistence."

    The sentence is about a *poor answer* — a specific one, already given, that
    someone is now trying to understand. So the criterion is not "spans exist";
    it is that starting from that answer you can reach an explanation. Three
    things have to hold, and each is asserted separately.

    **Traced through all four stages.** Every stage the sentence names emits a
    span, and they share one trace — so following the answer takes you through
    context construction, model execution, guardrails and persistence rather
    than to four disconnected facts. `CRITERION_STAGES` maps the sentence's four
    words to the spans that make each visible; this test reads that map rather
    than a copy of it, so the instrumentation and the criterion cannot drift
    apart.

    **Reachable from the answer.** A trace nobody can find explains nothing. The
    answer's own row carries the `trace_id` — that is what `model_run` and
    `message.model_run_id` are for, and it is what the UI's trace link is built
    from. Asserted as a schema-level fact, since a live Phoenix is not available
    on every `make status`.

    **Says what went wrong.** A trace where a failed call looks successful is
    worse than no trace, because it actively misleads the person debugging. The
    model span carries an error status and the exception when the call fails.

    **No model, no network, no Phoenix.** Spans are collected in-process with an
    in-memory exporter, which is exactly why `configure_tracing` still installs a
    provider when no endpoint is set — instrumentation that only existed when a
    collector was reachable would make this criterion unassertable, and would
    mean the traced path and the tested path were different code.
    """
    from langchain_core.messages import HumanMessage
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.memory import InMemorySaver

    from ai_core.graphs import chat as chat_module
    from ai_core.graphs.chat import (
        PERSIST_KEY,
        RECORD_RUN_KEY,
        ChatState,
        GraphError,
        build_chat_graph,
    )
    from ai_core.models.gateway import GatewayError
    from ai_core.safety.decisions import SafetyDecision, SafetyOutcome, SafetyStage
    from ai_core.schemas.completion import CompletionResponse, FinalChunk, TokenChunk
    from ai_core.schemas.model_run import ModelRun as ModelRunFacts
    from ai_core.telemetry import Attr, capture_spans, configure_tracing, span
    from ai_core.telemetry.spans import CHAT_REQUEST, CRITERION_STAGES, LLM_GENERATE
    from database.models import Message, ModelRun

    # Idempotent: `api.main` may already have installed a provider, in which case
    # this returns None and the existing one is used. Called here so the test
    # passes when run alone, which is how `make status` runs it.
    configure_tracing()

    def run_graph(*, failing: bool = False) -> tuple[list[Any], list[ModelRunFacts]]:
        """Answer one question with span capture on; return spans and runs."""
        runs: list[ModelRunFacts] = []

        async def fake_stream(request: Any) -> Any:
            yield TokenChunk(text="an ")
            if failing:
                # A provider that dies mid-stream: the case where the trace is
                # the only record of what happened.
                raise GatewayError("the provider hung up")
            yield TokenChunk(text="answer")
            yield FinalChunk(
                response=CompletionResponse(
                    alias=request.alias,
                    provider_model="gpt-4o-mini",
                    text="an answer",
                    input_tokens=29,
                    output_tokens=86,
                    finish_reason="stop",
                )
            )

        async def allowed(*args: Any) -> SafetyOutcome:
            stage = SafetyStage.INPUT if len(args) == 1 else SafetyStage.OUTPUT
            return SafetyOutcome(
                stage=stage, decisions=[SafetyDecision.allow(stage, "stub", "stub@1")]
            )

        async def persist_answer(answer: CompletionResponse, model_run_id: str | None) -> str:
            return "stored-id"

        async def record_run(facts: ModelRunFacts) -> str:
            runs.append(facts)
            return "run-id"

        async def go() -> None:
            compiled = build_chat_graph().compile(checkpointer=InMemorySaver())
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": f"phase5-{failing}",
                    PERSIST_KEY: persist_answer,
                    RECORD_RUN_KEY: record_run,
                }
            }
            await compiled.ainvoke(
                ChatState(chat_id="phase-5", messages=[HumanMessage(content="why?")]),
                config=config,
            )

        module: Any = chat_module
        patched = {"stream": fake_stream, "check_input": allowed, "check_output": allowed}
        originals = {name: getattr(module, name) for name in patched}
        for name, replacement in patched.items():
            setattr(module, name, replacement)
        try:
            # The caller opens `chat.request`, exactly as the endpoint does. That
            # is the contract rather than an artefact of the test: the graph's
            # nodes nest their spans under whatever is current, so trace coherence
            # comes from the caller having opened a root. Run without one — which
            # nothing in the application does — and each node becomes its own
            # root, which is what a first draft of this test discovered by
            # producing five separate traces for one answer.
            with capture_spans() as spans, span(CHAT_REQUEST):
                try:
                    asyncio.run(go())
                except (GatewayError, GraphError):
                    # Expected on the failing path, and caught here for the same
                    # reason the SSE handler catches it: the request ended, the
                    # spans are the record of how. Routing (Phase 10) wraps the
                    # underlying GatewayError in a GraphError before it escapes,
                    # so both are tolerated.
                    if not failing:
                        raise
        finally:
            for name, original in originals.items():
                setattr(module, name, original)
        return spans, runs

    spans, runs = run_graph()
    emitted = {span.name for span in spans}

    # --- traced through all four stages ----------------------------------------
    for stage, required in CRITERION_STAGES.items():
        # `load_conversation` belongs to the endpoint, not the graph, so only the
        # graph's half of "context construction" is expected from a graph run.
        # apps/api/tests/test_tracing.py asserts the endpoint's half against the
        # real app; splitting it keeps this test free of an HTTP client and a
        # database while still covering the whole sentence between them.
        expected = [name for name in required if name != "load_conversation"]
        missing = [name for name in expected if name not in emitted]
        assert not missing, f"{stage} is not traceable: {missing} missing from {sorted(emitted)}"

    # --- one trace, not four disconnected facts --------------------------------
    trace_ids = {span.context.trace_id for span in spans if span.context is not None}
    assert len(trace_ids) == 1, (
        f"the stages are spread over {len(trace_ids)} traces; following an answer "
        f"through them would mean four separate lookups, not one"
    )

    # --- the model span carries what the call cost -----------------------------
    generate = next(span for span in spans if span.name == LLM_GENERATE)
    attributes = generate.attributes or {}
    assert attributes[Attr.INPUT_TOKENS] == 29
    assert attributes[Attr.OUTPUT_TOKENS] == 86
    assert attributes[Attr.PROVIDER_MODEL] == "gpt-4o-mini"
    # Priced, because `gpt-4o-mini` is in the table. The assertion is that a cost
    # was computed at all — the exact figure belongs to the pricing tests.
    assert float(attributes[Attr.ESTIMATED_COST]) > 0

    # --- reachable from the answer ---------------------------------------------
    # The run records the trace it happened inside, so the row a person is
    # looking at names the trace that explains it.
    assert len(runs) == 1
    assert runs[0].trace_id in {f"{trace_id:032x}" for trace_id in trace_ids}
    assert runs[0].operation == "chat.answer"

    # And the schema carries that link the other way: message -> run -> trace.
    assert "model_run_id" in Message.__table__.columns
    assert "trace_id" in ModelRun.__table__.columns
    assert ModelRun.__table__.columns["trace_id"].index is True, (
        "trace_id must be indexed; 'find the run for this trace' is the lookup "
        "the criterion turns into a click"
    )

    # --- says what went wrong --------------------------------------------------
    failed_spans, _no_runs = run_graph(failing=True)
    failed_generate = next(span for span in failed_spans if span.name == LLM_GENERATE)
    assert failed_generate.status.is_ok is False, (
        "a failed model call left an OK span; a trace that makes a failure look "
        "successful misleads the person debugging rather than helping them"
    )
    assert "hung up" in (failed_generate.status.description or "")
    # And the guardrail stage before it still ran and still recorded — the trace
    # shows how far the request got, which is the first thing you want to know.
    assert CRITERION_STAGES["guardrails"][0] in {span.name for span in failed_spans}
