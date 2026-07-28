"""Phase 4 — Safety pipeline

See docs/SPEC.md, "Phase 4 — Safety pipeline" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytestmark = pytest.mark.phase


@pytest.mark.phase
def test_phase_4_exit_criterion() -> None:
    """Phase 4 — Safety pipeline.

    Exit criterion (verbatim, docs/SPEC.md):

        "Every model interaction has an explicit, testable safety path."

    Three words carry the weight, and each is asserted separately.

    **Every** — asserted by walking the compiled chat graph rather than by
    listing the paths, because a list is a claim about the graph and a traversal
    is a fact about it. Every route from START to the model call passes through
    `input_safety_check`; every route from the model call to persistence passes
    through `output_safety_check`. There is no unchecked path because there is no
    path the traversal did not visit.

    The second model call in the system — the summariser — is covered
    transitively, and that argument is asserted rather than left in a comment:
    its input is the transcript, and nothing reaches the transcript without
    passing the output check, so it cannot be fed content the pipeline refused.
    Its own output is gated by the approval interrupt, which no model can resume
    (CLAUDE.md invariant #5).

    **Explicit** — an allowed interaction records its decisions too. This is the
    half that is easy to skip and the one the wording insists on: if only
    refusals were recorded, "checked and found fine" would be indistinguishable
    from "never checked", and the audit trail could not answer the question it
    exists for.

    **Testable** — every assertion below runs on constructed values and stubbed
    checks. The decision model is pure data, the routing is a pure function of
    state, and both refusal edges are structural. Nothing here needs a judge
    model, a network, or a database — the same contract as the earlier phase
    tests. The live rails are exercised separately, against a running gateway.
    """
    from langchain_core.messages import HumanMessage
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START

    from ai_core.graphs import chat as chat_module
    from ai_core.graphs.chat import (
        BLOCKED,
        PERSIST_KEY,
        RECORD_SAFETY_KEY,
        ChatState,
        build_chat_graph,
    )
    from ai_core.graphs.summary import NODE_SEQUENCE as SUMMARY_SEQUENCE
    from ai_core.safety.decisions import SafetyAction, SafetyDecision, SafetyOutcome, SafetyStage
    from ai_core.schemas.completion import CompletionResponse, FinalChunk, TokenChunk

    graph = build_chat_graph().compile().get_graph()
    edges: dict[str, list[Any]] = {}
    for edge in graph.edges:
        edges.setdefault(edge.source, []).append(edge)

    def paths(start: str, goal: str) -> list[list[str]]:
        """Every acyclic route from `start` to `goal`, as node-name lists.

        Exhaustive rather than sampled: the claim is about *every* interaction,
        so a traversal that stopped at the first route would prove nothing.
        """
        found: list[list[str]] = []

        def walk(node: str, seen: list[str]) -> None:
            if node == goal:
                found.append([*seen, node])
                return
            for edge in edges.get(node, []):
                if edge.target not in seen:
                    walk(edge.target, [*seen, node])

        walk(start, [])
        return found

    # --- every: the input check is unavoidable ---------------------------------
    to_model = paths(START, "generate_answer")
    assert to_model, "no path reaches the model call; the traversal is wrong, not the graph"
    for path in to_model:
        assert "input_safety_check" in path, path

    # --- every: the output check is unavoidable --------------------------------
    to_storage = paths(START, "persist")
    assert to_storage
    for path in to_storage:
        assert "output_safety_check" in path, path
        # Ordering matters as much as presence: a check that ran *after* the write
        # would be a report, not a gate.
        assert path.index("output_safety_check") < path.index("persist"), path

    # --- every: a refusal ends the run -----------------------------------------
    # Not "sets a flag that persist consults" — `persist` is unreachable from a
    # refusal, so there is no code path left in which a blocked answer is stored.
    for source in ("input_safety_check", "output_safety_check"):
        refusals = [edge for edge in edges[source] if edge.data == BLOCKED]
        assert [edge.target for edge in refusals] == [END], source

    # --- every: the summariser reads only already-checked content --------------
    # The transcript is the only thing the summary graph reads, and the assertion
    # above proves nothing enters the transcript unchecked. What remains is that
    # its *output* cannot become knowledge on its own.
    assert SUMMARY_SEQUENCE.index("await_approval") < SUMMARY_SEQUENCE.index("apply_decision")

    # --- explicit and testable: run the graph, checks stubbed ------------------
    def run(
        *, on_input: SafetyAction, on_output: SafetyAction
    ) -> tuple[dict[str, Any], list[SafetyOutcome], list[str]]:
        recorded: list[SafetyOutcome] = []
        stored: list[str] = []

        def outcome(stage: SafetyStage, action: SafetyAction) -> SafetyOutcome:
            if action is SafetyAction.ALLOW:
                return SafetyOutcome(
                    stage=stage, decisions=[SafetyDecision.allow(stage, "stub", "stub@1")]
                )
            return SafetyOutcome(
                stage=stage,
                decisions=[
                    SafetyDecision.refuse(
                        stage,
                        "stub",
                        "stub@1",
                        action=action,
                        categories=["testing"],
                        explanation="stubbed refusal",
                    )
                ],
            )

        async def fake_stream(request: Any) -> Any:
            yield TokenChunk(text="an ")
            yield TokenChunk(text="answer")
            yield FinalChunk(
                response=CompletionResponse(
                    alias=request.alias,
                    provider_model="stub-model",
                    text="an answer",
                    input_tokens=1,
                    output_tokens=2,
                    finish_reason="stop",
                )
            )

        async def fake_input(text: str) -> SafetyOutcome:
            return outcome(SafetyStage.INPUT, on_input)

        async def fake_output(question: str, answer: str) -> SafetyOutcome:
            return outcome(SafetyStage.OUTPUT, on_output)

        async def persist_answer(answer: CompletionResponse) -> str:
            stored.append(answer.text)
            return "stored-id"

        async def record_safety(result: SafetyOutcome) -> None:
            recorded.append(result)

        async def go() -> dict[str, Any]:
            compiled = build_chat_graph().compile(checkpointer=InMemorySaver())
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": f"phase4-{on_input.value}-{on_output.value}",
                    PERSIST_KEY: persist_answer,
                    RECORD_SAFETY_KEY: record_safety,
                }
            }
            values: dict[str, Any] = await compiled.ainvoke(
                ChatState(chat_id="phase-4", messages=[HumanMessage(content="a question")]),
                config=config,
            )
            return values

        # `monkeypatch` is a fixture and these phase tests take none — they are
        # deliberately callable as plain functions. Restoring by hand is the cost.
        # Typed as `Any` because module attributes are not writable in mypy's view
        # of a module; the alternative is three separate ignores saying the same
        # thing.
        module: Any = chat_module
        patched = {"stream": fake_stream, "check_input": fake_input, "check_output": fake_output}
        originals = {name: getattr(module, name) for name in patched}
        for name, replacement in patched.items():
            setattr(module, name, replacement)
        try:
            final = asyncio.run(go())
        finally:
            for name, original in originals.items():
                setattr(module, name, original)
        return final, recorded, stored

    # Explicit: the uneventful case still leaves a record, at both stages.
    final, recorded, stored = run(on_input=SafetyAction.ALLOW, on_output=SafetyAction.ALLOW)
    assert stored == ["an answer"]
    assert [result.stage for result in recorded] == [SafetyStage.INPUT, SafetyStage.OUTPUT]
    assert all(not result.blocks for result in recorded)
    # An audit row that cannot say which rules produced it is a claim, not a record.
    assert all(
        decision.policy_name and decision.policy_version
        for result in recorded
        for decision in result.decisions
    )

    # Testable: a refused question costs nothing and stores nothing.
    final, recorded, stored = run(on_input=SafetyAction.BLOCK, on_output=SafetyAction.ALLOW)
    assert stored == []
    assert final["blocked_at"] == SafetyStage.INPUT
    assert [result.stage for result in recorded] == [SafetyStage.INPUT]  # never reached the model

    # Testable: a refused answer is recorded and not persisted. Its tokens did
    # stream — the check runs after generation, which is the documented cost of
    # streaming — but the transcript never receives it, so no summary, draft or
    # Learning can be built from it.
    final, recorded, stored = run(on_input=SafetyAction.ALLOW, on_output=SafetyAction.BLOCK)
    assert stored == []
    assert final.get("persisted_message_id") is None
    assert final["blocked_at"] == SafetyStage.OUTPUT
    assert [result.stage for result in recorded] == [SafetyStage.INPUT, SafetyStage.OUTPUT]

    # A warning is not a refusal. PII in a question is usually the user's own
    # data, and refusing to help someone with their own config file would be the
    # wrong trade — so this path must stay open, and stay recorded.
    final, recorded, stored = run(
        on_input=SafetyAction.ALLOW_WITH_WARNING, on_output=SafetyAction.ALLOW
    )
    assert stored == ["an answer"]
    assert final["blocked_at"] is None
    assert recorded[0].action is SafetyAction.ALLOW_WITH_WARNING

    # --- the audit trail can hold what was recorded ----------------------------
    from database.models import SafetyEvent

    columns = set(SafetyEvent.__table__.columns.keys())
    assert {"stage", "policy_name", "policy_version", "action", "severity", "categories"} <= columns
    # Nullable because a blocked interaction has no message: that row is the only
    # record the event ever happened, which is the case the table exists for.
    assert SafetyEvent.__table__.columns["message_id"].nullable
