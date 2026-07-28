"""Contract for the chat workflow graph.

No Postgres and no model: the graph takes its persistence through an injected
callable and its answers through the gateway, and both are substituted here. That
is the payoff of `ai_core.graphs.chat` importing neither `database` nor a
provider — the whole workflow is exercisable as a function of its inputs.

An in-memory checkpointer stands in for the Postgres one. What is being asserted
is the *shape* of an execution — which nodes run, in what order, carrying what —
and that does not depend on where checkpoints are stored. The Postgres path is
covered by the Phase 2 exit-criterion test.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END

from ai_core.graphs import chat as chat_module
from ai_core.graphs.chat import (
    BLOCKED,
    BRANCHING_NODES,
    CONTINUE,
    NODE_SEQUENCE,
    PERSIST_KEY,
    RECORD_SAFETY_KEY,
    ChatState,
    GraphError,
    build_chat_graph,
    route_after_safety,
)
from ai_core.models.aliases import ModelAlias
from ai_core.safety.decisions import SafetyAction, SafetyDecision, SafetyOutcome, SafetyStage
from ai_core.schemas.completion import CompletionResponse, FinalChunk, TokenChunk

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def allow_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both safety checks pass, unless a test says otherwise.

    Autouse because the checks now sit on the default path and each one is a real
    model call. Stubbing them here keeps this file's promise — no model, no
    Postgres — and leaves every existing test asserting what it always asserted.
    The checks' own logic is tested in test_safety.py; what this file tests is the
    graph's reaction to their verdicts.
    """
    _stub_safety(monkeypatch)


def _outcome(stage: SafetyStage, action: SafetyAction = SafetyAction.ALLOW) -> SafetyOutcome:
    if action is SafetyAction.ALLOW:
        return SafetyOutcome(stage=stage, decisions=[SafetyDecision.allow(stage, "stub", "v1")])
    return SafetyOutcome(
        stage=stage,
        decisions=[
            SafetyDecision.refuse(
                stage,
                "stub",
                "v1",
                action=action,
                categories=["testing"],
                explanation=f"stubbed {action.value}",
            )
        ],
    )


def _stub_safety(
    monkeypatch: pytest.MonkeyPatch,
    *,
    on_input: SafetyAction = SafetyAction.ALLOW,
    on_output: SafetyAction = SafetyAction.ALLOW,
) -> None:
    async def fake_input(text: str) -> SafetyOutcome:
        return _outcome(SafetyStage.INPUT, on_input)

    async def fake_output(question: str, answer: str) -> SafetyOutcome:
        return _outcome(SafetyStage.OUTPUT, on_output)

    monkeypatch.setattr(chat_module, "check_input", fake_input)
    monkeypatch.setattr(chat_module, "check_output", fake_output)


def _answer(text: str = "an answer", finish_reason: str = "stop") -> CompletionResponse:
    return CompletionResponse(
        alias=ModelAlias.LEARNING_FAST,
        provider_model="stub-model",
        text=text,
        input_tokens=5,
        output_tokens=3,
        finish_reason=finish_reason,
    )


def _stub_gateway(
    monkeypatch: pytest.MonkeyPatch,
    *,
    parts: list[str],
    answer: CompletionResponse | None = None,
    omit_final: bool = False,
) -> list[Any]:
    """Replace the gateway stream; return the list requests are recorded into."""
    seen: list[Any] = []

    async def fake_stream(request: Any) -> AsyncIterator[Any]:
        seen.append(request)
        for part in parts:
            yield TokenChunk(text=part)
        if not omit_final:
            yield FinalChunk(response=answer or _answer("".join(parts)))

    monkeypatch.setattr(chat_module, "stream", fake_stream)
    return seen


async def _run(
    state: ChatState, *, thread: str = "t1", recorded: list[SafetyOutcome] | None = None
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Run the graph to completion; return final values, tokens, and stored ids."""
    stored: list[str] = []

    async def persist_answer(answer: CompletionResponse, model_run_id: str | None) -> str:
        stored.append(answer.text)
        return "stored-id"

    async def record_safety(outcome: SafetyOutcome) -> None:
        if recorded is not None:
            recorded.append(outcome)

    graph = build_chat_graph().compile(checkpointer=InMemorySaver())
    config: RunnableConfig = {
        "configurable": {
            "thread_id": thread,
            PERSIST_KEY: persist_answer,
            RECORD_SAFETY_KEY: record_safety,
        }
    }

    tokens: list[str] = []
    async for mode, payload in graph.astream(state, config=config, stream_mode=["custom"]):
        # `isinstance` rather than a bare key check: with a list `stream_mode`
        # LangGraph types the payload loosely, so narrowing here is what keeps
        # this readable to mypy and safe if another mode is ever added.
        if mode == "custom" and isinstance(payload, dict) and "token" in payload:
            tokens.append(payload["token"])

    final = (await graph.aget_state(config)).values
    return final, tokens, stored


# --- shape ---------------------------------------------------------------------


def test_the_graph_is_the_nodes_the_spec_names() -> None:
    compiled = build_chat_graph().compile()
    nodes = [n for n in compiled.get_graph().nodes if not n.startswith("__")]
    assert nodes == list(NODE_SEQUENCE)


def test_only_the_safety_checks_branch() -> None:
    """Phase 2 asserted *no* node had more than one outgoing edge.

    Phase 4 changes that assertion rather than dropping it, which is what the
    original test existed to force. The rule is now narrower and says more: the
    two safety checks branch, and nothing else does. A conditional edge added
    anywhere else — Phase 10's model routing, say — still has to come here and
    argue for itself.
    """
    compiled = build_chat_graph().compile()
    outgoing: dict[str, int] = {}
    for edge in compiled.get_graph().edges:
        outgoing[edge.source] = outgoing.get(edge.source, 0) + 1

    branching = {source for source, count in outgoing.items() if count > 1}
    assert branching == set(BRANCHING_NODES), outgoing
    assert all(outgoing[node] == 2 for node in BRANCHING_NODES), outgoing


def test_a_blocked_check_routes_to_the_end() -> None:
    """The refusal edge is the enforcement, so it is asserted structurally too.

    `route_after_safety` is a pure function of state: this pins both answers
    without running the graph or spending a model call.
    """
    blocked = ChatState(chat_id="c", blocked_at=SafetyStage.INPUT)
    assert route_after_safety(blocked) == BLOCKED
    assert route_after_safety(ChatState(chat_id="c")) == CONTINUE


def test_a_blocked_answer_cannot_reach_persistence() -> None:
    """The one structural claim the whole phase rests on.

    Not "persist checks a flag" — `persist` is not reachable from a blocked
    output check at all. A refused answer leaves no message row, so no summary,
    draft or Learning can ever be derived from it (CLAUDE.md invariant #5).
    """
    graph = build_chat_graph().compile().get_graph()
    from_output = {edge.target for edge in graph.edges if edge.source == "output_safety_check"}
    assert from_output == {"persist", END}

    blocked_edges = [
        edge for edge in graph.edges if edge.source in BRANCHING_NODES and edge.data == BLOCKED
    ]
    assert {edge.target for edge in blocked_edges} == {END}


# --- execution -----------------------------------------------------------------


async def test_a_run_walks_the_nodes_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_gateway(monkeypatch, parts=["hi"])
    stored: list[str] = []

    async def persist_answer(answer: CompletionResponse, model_run_id: str | None) -> str:
        stored.append(answer.text)
        return "stored-id"

    graph = build_chat_graph().compile(checkpointer=InMemorySaver())
    config: RunnableConfig = {"configurable": {"thread_id": "ordered", PERSIST_KEY: persist_answer}}
    state = ChatState(chat_id="c1", messages=[HumanMessage(content="a question")])
    async for _ in graph.astream(state, config=config, stream_mode=["custom"]):
        pass

    # The checkpoint history is the record of the execution. Read oldest-first,
    # each entry's `next` names the node about to run — which is exactly the
    # "visible as a deterministic graph execution" the criterion asks for.
    history = [entry async for entry in graph.aget_state_history(config)]
    upcoming = [entry.next[0] for entry in reversed(history) if entry.next]
    assert upcoming == ["__start__", *NODE_SEQUENCE]


async def test_tokens_stream_out_and_the_answer_is_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_gateway(monkeypatch, parts=["one ", "two ", "three"])
    final, tokens, stored = await _run(
        ChatState(chat_id="c1", messages=[HumanMessage(content="count")])
    )

    assert tokens == ["one ", "two ", "three"]
    assert stored == ["one two three"]
    assert final["persisted_message_id"] == "stored-id"
    # The answer joins the transcript, so a reader of the checkpoint sees the
    # conversation rather than only the question.
    assert [type(m).__name__ for m in final["messages"]] == ["HumanMessage", "AIMessage"]


async def test_choose_model_picks_the_alias_by_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _stub_gateway(monkeypatch, parts=["x"])
    await _run(ChatState(chat_id="c1", messages=[HumanMessage(content="q")]))

    # The request reaching the gateway names an alias, never a provider model.
    assert seen[0].alias is ModelAlias.LEARNING_FAST


async def test_build_context_sends_the_whole_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 1's strategy, now isolated in a node (docs/SPEC.md §14).

    Asserted because it is a choice rather than an accident — Phase 2's successor
    strategies (recent window, summary-plus-recent) land in that node, and this
    is what notices.
    """
    seen = _stub_gateway(monkeypatch, parts=["x"])
    await _run(
        ChatState(
            chat_id="c1",
            messages=[
                HumanMessage(content="first"),
                AIMessage(content="answer"),
                HumanMessage(content="second"),
            ],
        )
    )
    assert [turn.content for turn in seen[0].messages] == ["first", "answer", "second"]
    assert [turn.role for turn in seen[0].messages] == ["user", "assistant", "user"]


# --- refusals ------------------------------------------------------------------


async def test_refuses_an_empty_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_gateway(monkeypatch, parts=["x"])
    with pytest.raises(GraphError, match="nothing to answer"):
        await _run(ChatState(chat_id="c1", messages=[]))


async def test_refuses_to_answer_its_own_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_gateway(monkeypatch, parts=["x"])
    with pytest.raises(GraphError, match="not a question"):
        await _run(
            ChatState(
                chat_id="c1",
                messages=[HumanMessage(content="q"), AIMessage(content="already answered")],
            )
        )


async def test_an_empty_answer_is_never_persisted(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty assistant turn would sit in the transcript saying nothing — and
    from Phase 3 the transcript is what a Learning is derived from."""
    _stub_gateway(monkeypatch, parts=["   "], answer=_answer("   "))
    with pytest.raises(GraphError, match="empty answer"):
        await _run(ChatState(chat_id="c1", messages=[HumanMessage(content="q")]))


async def test_a_stream_that_never_finishes_persists_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_gateway(monkeypatch, parts=["half"], omit_final=True)
    with pytest.raises(GraphError, match="ended before it completed"):
        await _run(ChatState(chat_id="c1", messages=[HumanMessage(content="q")]))


async def test_the_graph_will_not_run_without_somewhere_to_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The graph does not know what storage is, but it does insist there be some.

    Without this the workflow would stream a perfectly good answer and drop it.
    """
    _stub_gateway(monkeypatch, parts=["x"])
    graph = build_chat_graph().compile(checkpointer=InMemorySaver())
    config: RunnableConfig = {"configurable": {"thread_id": "no-persist"}}
    state = ChatState(chat_id="c1", messages=[HumanMessage(content="q")])

    with pytest.raises(GraphError, match=PERSIST_KEY):
        async for _ in graph.astream(state, config=config, stream_mode=["custom"]):
            pass


# --- safety --------------------------------------------------------------------


async def test_a_blocked_question_never_reaches_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The input check is placed early precisely so a refusal costs nothing."""
    seen = _stub_gateway(monkeypatch, parts=["should not happen"])
    _stub_safety(monkeypatch, on_input=SafetyAction.BLOCK)

    final, tokens, stored = await _run(
        ChatState(chat_id="c1", messages=[HumanMessage(content="something forbidden")])
    )

    assert seen == []  # no generation request was ever built
    assert tokens == []
    assert stored == []
    assert final["blocked_at"] == SafetyStage.INPUT


async def test_a_blocked_answer_is_not_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tokens escaped; the transcript did not.

    This is the honest shape of streaming plus an output check, and asserting it
    keeps the trade-off documented in behaviour rather than only in a comment.
    """
    _stub_gateway(monkeypatch, parts=["bad ", "answer"])
    _stub_safety(monkeypatch, on_output=SafetyAction.BLOCK)

    final, tokens, stored = await _run(
        ChatState(chat_id="c1", messages=[HumanMessage(content="a question")])
    )

    assert tokens == ["bad ", "answer"]  # already shown, unavoidably
    assert stored == []  # but never persisted
    # Absent rather than None: `persist` never ran, so nothing ever wrote the key.
    assert final.get("persisted_message_id") is None
    assert final["blocked_at"] == SafetyStage.OUTPUT


async def test_a_blocked_answer_tells_the_caller_to_discard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Because the caller has already rendered it, silence would leave it on screen."""
    _stub_gateway(monkeypatch, parts=["bad"])
    _stub_safety(monkeypatch, on_output=SafetyAction.BLOCK)

    graph = build_chat_graph().compile(checkpointer=InMemorySaver())
    config: RunnableConfig = {"configurable": {"thread_id": "discard", PERSIST_KEY: _unused}}
    events: list[dict[str, Any]] = []
    async for mode, payload in graph.astream(
        ChatState(chat_id="c1", messages=[HumanMessage(content="q")]),
        config=config,
        stream_mode=["custom"],
    ):
        if mode == "custom" and isinstance(payload, dict) and "safety" in payload:
            events.append(payload["safety"])

    assert [event["stage"] for event in events] == [SafetyStage.OUTPUT.value]
    assert events[0]["discard"] is True


async def test_both_stages_are_recorded_when_nothing_is_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exit criterion is an *explicit* path, not merely a path that stops bad things.

    An allowed interaction that recorded nothing would be indistinguishable from
    one that was never checked.
    """
    _stub_gateway(monkeypatch, parts=["fine"])
    recorded: list[SafetyOutcome] = []
    await _run(ChatState(chat_id="c1", messages=[HumanMessage(content="q")]), recorded=recorded)

    assert [outcome.stage for outcome in recorded] == [SafetyStage.INPUT, SafetyStage.OUTPUT]
    assert all(not outcome.blocks for outcome in recorded)


async def test_a_warning_does_not_stop_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """PII in a question is the user's own data; refusing to help with it would be wrong."""
    _stub_gateway(monkeypatch, parts=["here you go"])
    _stub_safety(monkeypatch, on_input=SafetyAction.ALLOW_WITH_WARNING)
    recorded: list[SafetyOutcome] = []

    final, _tokens, stored = await _run(
        ChatState(chat_id="c1", messages=[HumanMessage(content="my key is sk-...")]),
        recorded=recorded,
    )

    assert stored == ["here you go"]
    assert final["blocked_at"] is None
    assert recorded[0].action is SafetyAction.ALLOW_WITH_WARNING


async def test_the_graph_runs_without_a_recorder(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing audit sink must not disable the check that protects the user."""
    _stub_gateway(monkeypatch, parts=["ok"])
    graph = build_chat_graph().compile(checkpointer=InMemorySaver())
    config: RunnableConfig = {"configurable": {"thread_id": "no-recorder", PERSIST_KEY: _unused}}
    final = await graph.ainvoke(
        ChatState(chat_id="c1", messages=[HumanMessage(content="q")]), config=config
    )
    assert final["persisted_message_id"] == "stored-id"


async def _unused(answer: CompletionResponse, model_run_id: str | None) -> str:
    return "stored-id"
