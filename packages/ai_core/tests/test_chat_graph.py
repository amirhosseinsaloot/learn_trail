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

from ai_core.graphs import chat as chat_module
from ai_core.graphs.chat import (
    NODE_SEQUENCE,
    PERSIST_KEY,
    ChatState,
    GraphError,
    build_chat_graph,
)
from ai_core.models.aliases import ModelAlias
from ai_core.schemas.completion import CompletionResponse, FinalChunk, TokenChunk

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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
    state: ChatState, *, thread: str = "t1"
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Run the graph to completion; return final values, tokens, and stored ids."""
    stored: list[str] = []

    async def persist_answer(answer: CompletionResponse) -> str:
        stored.append(answer.text)
        return "stored-id"

    graph = build_chat_graph().compile(checkpointer=InMemorySaver())
    config: RunnableConfig = {"configurable": {"thread_id": thread, PERSIST_KEY: persist_answer}}

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


def test_the_graph_is_the_five_nodes_the_spec_names() -> None:
    compiled = build_chat_graph().compile()
    nodes = [n for n in compiled.get_graph().nodes if not n.startswith("__")]
    assert nodes == list(NODE_SEQUENCE)


def test_the_graph_has_no_branches() -> None:
    """Determinism is the Phase 2 criterion, so it is asserted structurally.

    Every node has exactly one outgoing edge. A conditional edge added later —
    Phase 4's safety pipeline can block, Phase 10 routes between models — must
    fail this test and be a deliberate change to it, not a silent one.
    """
    compiled = build_chat_graph().compile()
    outgoing: dict[str, int] = {}
    for edge in compiled.get_graph().edges:
        outgoing[edge.source] = outgoing.get(edge.source, 0) + 1
    assert all(count == 1 for count in outgoing.values()), outgoing


# --- execution -----------------------------------------------------------------


async def test_a_run_walks_the_nodes_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_gateway(monkeypatch, parts=["hi"])
    stored: list[str] = []

    async def persist_answer(answer: CompletionResponse) -> str:
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
