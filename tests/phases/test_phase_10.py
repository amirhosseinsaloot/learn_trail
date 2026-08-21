"""Phase 10 — Model routing

See docs/SPEC.md, "Phase 10 — Model routing" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

pytestmark = pytest.mark.phase


@pytest.mark.phase
def test_phase_10_exit_criterion() -> None:
    """Phase 10 — Model routing.

    docs/SPEC.md states no verbatim exit criterion for this phase; the plan's
    proxy is used (plans/phase-10.md):

        "A request through the difficulty classifier is routed to the cheap-model
        path for a simple question and the strong-model path for a difficult one,
        and a forced timeout triggers the documented fallback strategy."

    Three claims, and the third is the one a router without a spine fails.

    **Simple routes cheap.** A definition or a lookup goes to `learning-fast`.

    **Difficult routes strong.** A question that asks the model to reason across
    several things — why, compare, design, a trade-off — goes to `learning-deep`.

    **A forced timeout triggers the fallback.** The strong model is made to hang;
    the graph abandons it after the timeout and serves the answer from the
    documented fallback (`learning-deep -> learning-fast`) instead. This is
    asserted by *running the real graph*, not by inspecting the map — a fallback
    that exists in a dict but is never consulted would pass a weaker test and fail
    a user.

    **No cloud model call.** The classifier is a pure rule and the gateway is
    stubbed. Routing spends nothing to decide, which is the point — a model call
    before every model call would double the latency floor to choose an alias.
    """
    from langchain_core.messages import HumanMessage
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.memory import InMemorySaver

    from ai_core.graphs import chat as chat_module
    from ai_core.graphs.chat import (
        GENERATION_TIMEOUT_KEY,
        PERSIST_KEY,
        ChatState,
        build_chat_graph,
    )
    from ai_core.models.aliases import ModelAlias
    from ai_core.models.routing import Difficulty, classify_difficulty, fallback_for, route
    from ai_core.schemas.completion import CompletionResponse, FinalChunk, TokenChunk

    # --- the classifier separates lookup from reasoning ------------------------
    assert classify_difficulty("What is a primary key?") is Difficulty.SIMPLE
    assert classify_difficulty("Why does a B-tree stay balanced?") is Difficulty.DIFFICULT

    # And routing maps each verdict to the documented alias.
    assert route("define an index")[1] is ModelAlias.LEARNING_FAST
    assert route("compare two indexing strategies")[1] is ModelAlias.LEARNING_DEEP

    # The fallback is documented and directional: strong -> fast, and the fast
    # model is the floor.
    assert fallback_for(ModelAlias.LEARNING_DEEP) is ModelAlias.LEARNING_FAST
    assert fallback_for(ModelAlias.LEARNING_FAST) is None

    # --- run the real graph for each of the three cases ------------------------
    def _answer(text: str) -> CompletionResponse:
        return CompletionResponse(
            alias=ModelAlias.LEARNING_FAST,
            provider_model="stub-model",
            text=text,
            input_tokens=5,
            output_tokens=3,
            finish_reason="stop",
        )

    async def _allow(*args: Any) -> Any:
        from ai_core.safety.decisions import SafetyDecision, SafetyOutcome, SafetyStage

        stage = SafetyStage.INPUT if len(args) == 1 else SafetyStage.OUTPUT
        return SafetyOutcome(stage=stage, decisions=[SafetyDecision.allow(stage, "stub", "v1")])

    def _run(question: str, *, hang_strong: bool) -> tuple[list[ModelAlias], dict[str, Any]]:
        seen: list[ModelAlias] = []

        async def fake_stream(request: Any) -> AsyncIterator[Any]:
            seen.append(request.alias)
            if hang_strong and request.alias is ModelAlias.LEARNING_DEEP:
                await asyncio.sleep(5)  # past the forced timeout, yielding nothing
                yield FinalChunk(response=_answer("never reached"))
            else:
                yield TokenChunk(text="answer")
                yield FinalChunk(response=_answer("answer"))

        async def persist_answer(answer: CompletionResponse, model_run_id: str | None) -> str:
            return "stored-id"

        # monkeypatch is a fixture; these phase tests take none. Restore by hand.
        module: Any = chat_module
        originals = {
            name: getattr(module, name) for name in ("stream", "check_input", "check_output")
        }
        module.stream = fake_stream
        module.check_input = _allow
        module.check_output = _allow
        try:
            graph = build_chat_graph().compile(checkpointer=InMemorySaver())
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": f"phase10-{question[:8]}-{hang_strong}",
                    PERSIST_KEY: persist_answer,
                    GENERATION_TIMEOUT_KEY: 0.2,
                }
            }

            async def go() -> dict[str, Any]:
                state = ChatState(chat_id="p10", messages=[HumanMessage(content=question)])
                async for _ in graph.astream(state, config=config, stream_mode=["custom"]):
                    pass
                return (await graph.aget_state(config)).values

            final = asyncio.run(go())
        finally:
            for name, original in originals.items():
                setattr(module, name, original)
        return seen, final

    # Simple question: one call, to the fast model.
    simple_seen, simple_final = _run("define a primary key", hang_strong=False)
    assert simple_seen == [ModelAlias.LEARNING_FAST]
    assert simple_final["difficulty"] == "simple"
    assert simple_final["used_fallback"] is False

    # Difficult question: one call, to the strong model.
    hard_seen, hard_final = _run("why is normalisation a trade-off?", hang_strong=False)
    assert hard_seen == [ModelAlias.LEARNING_DEEP]
    assert hard_final["difficulty"] == "difficult"

    # Difficult question with the strong model hanging: strong is tried, times
    # out, and the fast model answers. This is the fallback strategy firing.
    fb_seen, fb_final = _run("compare A and B and explain why", hang_strong=True)
    assert fb_seen == [ModelAlias.LEARNING_DEEP, ModelAlias.LEARNING_FAST], (
        "the strong model timed out but the fallback was not tried — a forced "
        "timeout must trigger the documented fallback, not fail the request"
    )
    assert fb_final["used_fallback"] is True
    assert fb_final["persisted_message_id"] is not None, (
        "the fallback produced no persisted answer, so the user got nothing on "
        "exactly the hard request routing existed to serve"
    )
