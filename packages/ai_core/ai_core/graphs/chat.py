"""The chat workflow as a LangGraph graph (docs/SPEC.md §15, Phase 2).

    validate_input -> build_context -> choose_model -> generate_answer -> persist

Phase 1 made this same sequence happen inside one endpoint function. Moving it
into a graph is not decoration: each step becomes a named, separately-inspectable
unit, the checkpointer records the state after every one of them, and the Phase 2
exit criterion — "each chat request is visible as a deterministic graph
execution" — becomes something you can assert rather than assume.

**Deterministic** is the load-bearing word. There are no conditional edges and no
model-chosen routing here: the same input always walks the same five nodes in the
same order. `choose_model` picks an alias by rule, not by asking a model. Later
phases add branches (the safety pipeline in Phase 4 can block, and Phase 10 routes
between models), and each of those is a deliberate change to this shape.

**This module does not import `database`.** Persistence enters through an
injected callable on the run config, so the graph can be exercised end to end
with no Postgres and no session. docs/ARCHITECTURE.md §7 would permit the import
— `ai_core` sits above `database` — but not needing it keeps every node a
function of its inputs, which is most of why the criterion is testable at all.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Final

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from ai_core.graphs.messages import context_from_langchain
from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import stream
from ai_core.schemas.completion import CompletionRequest, CompletionResponse, FinalChunk, TokenChunk

#: Key under which the caller supplies the persistence callable (see module
#: docstring). Injected through `config["configurable"]` — LangGraph's standard
#: channel for per-run values that are not part of graph state.
PERSIST_KEY: Final = "persist_answer"

#: Signature of that callable: given the finished answer, store it and return the
#: id of the row created. Async because the caller's session is async.
PersistAnswer = Callable[[CompletionResponse], Awaitable[str]]


class GraphError(RuntimeError):
    """The workflow could not complete.

    Distinct from `GatewayError`, which means the provider call itself failed.
    This is the graph declining to produce a result — and the distinction matters
    because only one of them is worth retrying.
    """


class GraphInputError(GraphError):
    """The request was never valid.

    Raised by `validate_input`. Separated from its parent so a caller can answer
    "was this my fault?" — this one maps to a 4xx, the base class does not.
    """


class ChatState(BaseModel):
    """Everything the workflow carries between nodes.

    A Pydantic model rather than a TypedDict so the state is validated at every
    boundary, consistent with CLAUDE.md invariant #4 — and so a node returning a
    misspelled key fails immediately instead of silently writing a field nothing
    reads.
    """

    #: The conversation so far. `add_messages` is LangGraph's reducer: a node
    #: returns only the messages it adds, and the reducer appends them (matching
    #: on id for updates). Without it, a node's return value would *replace* the
    #: whole list, and `generate_answer` would silently discard the transcript.
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    #: Which chat this run belongs to. Also the checkpointer's thread id, which
    #: is what makes a resumed conversation resume the right graph state.
    chat_id: str

    #: The subset of `messages` chosen for this request — the working context of
    #: docs/ARCHITECTURE.md §6, kept separate from the transcript because they
    #: are different things.
    context: list[BaseMessage] = Field(default_factory=list)

    #: Chosen by `choose_model`. A role, never a provider model string.
    alias: ModelAlias | None = None

    #: Set by `generate_answer`, consumed by `persist`.
    answer: CompletionResponse | None = None

    #: Set by `persist` — evidence the answer reached storage.
    persisted_message_id: str | None = None


async def validate_input(state: ChatState) -> dict[str, Any]:
    """Refuse a request that cannot sensibly be answered.

    The cheapest node, deliberately first: everything after it costs either a
    database round trip or money. In Phase 4 this is where the input half of the
    safety pipeline attaches (size and format checks, injection detection, PII) —
    the node exists now so that arrival is an edit rather than a re-plumbing.
    """
    if not state.messages:
        raise GraphInputError("there is nothing to answer: the conversation is empty")
    if not isinstance(state.messages[-1], HumanMessage):
        raise GraphInputError("the last message is not a question; the model would answer itself")
    return {}


async def build_context(state: ChatState) -> dict[str, Any]:
    """Choose what the model actually sees.

    Phase 1's strategy, unchanged and now isolated: the full transcript
    (docs/SPEC.md §14 lists it first). It is correct for short chats and will
    stop being correct — a recent-message window, previous-summary-plus-recent,
    or relevance-selected context are the documented successors, and this node is
    where each of them lands. Approved Learnings become part of this selection in
    Phase 8.
    """
    return {"context": list(state.messages)}


async def choose_model(state: ChatState) -> dict[str, Any]:
    """Pick the alias for this request.

    A rule, not a model call — that is what keeps the graph deterministic. Phase
    10 turns this into real routing (by length, cost, or difficulty); until then
    every chat answer is `learning-fast`, and stating that in its own node is
    what makes the eventual change a one-node diff.
    """
    return {"alias": ModelAlias.LEARNING_FAST}


async def generate_answer(state: ChatState) -> dict[str, Any]:
    """Call the model through the gateway, streaming tokens out as they arrive.

    Tokens are emitted on LangGraph's `custom` stream channel via
    `get_stream_writer()`. That is what lets the SSE endpoint stream a graph
    execution: without it the caller would only see state updates after each node
    finished, and a streamed answer would arrive as one lump at the end.
    """
    if state.alias is None:  # pragma: no cover - unreachable via the compiled graph
        raise GraphInputError("choose_model did not run before generate_answer")

    writer = get_stream_writer()
    request = CompletionRequest(alias=state.alias, messages=context_from_langchain(state.context))

    answer: CompletionResponse | None = None
    async for chunk in stream(request):
        if isinstance(chunk, TokenChunk):
            writer({"token": chunk.text})
        elif isinstance(chunk, FinalChunk):
            answer = chunk.response

    if answer is None:
        # The stream ended without a final chunk: the connection died rather than
        # the model finishing. Returning here would let `persist` store a
        # truncated answer as if it were complete.
        raise GraphError("the model stream ended before it completed")

    if answer.is_empty:
        # A model may legitimately return nothing, but an empty assistant turn is
        # not worth storing — it would sit in the transcript as a turn that said
        # nothing, and from Phase 3 the transcript is what a Learning is derived
        # from. Raising here means `persist` never runs, which is the behaviour
        # Phase 1's endpoint had and which the graph must not quietly drop.
        raise GraphError("the model returned an empty answer")

    # The answer joins `messages` as well as `answer`, so the checkpointed
    # transcript is the real one — which is what a resumed thread reads back.
    return {"answer": answer, "messages": [AIMessage(content=answer.text)]}


async def persist(state: ChatState, config: RunnableConfig) -> dict[str, Any]:
    """Store the answer, through the callable the caller injected.

    The graph does not know what storage is. It knows there is something that
    turns a finished answer into a durable id, and that this is the last step —
    which is precisely the property that makes "the answer was saved" checkable
    from a graph trace.
    """
    if state.answer is None:  # pragma: no cover - unreachable via the compiled graph
        raise GraphInputError("generate_answer did not produce an answer")

    configurable: dict[str, Any] = config.get("configurable") or {}
    persist_answer: PersistAnswer | None = configurable.get(PERSIST_KEY)
    if persist_answer is None:
        raise GraphInputError(
            f"no {PERSIST_KEY!r} in the run config; the graph cannot store its own answer"
        )
    return {"persisted_message_id": await persist_answer(state.answer)}


#: The node order, as one list. Named so the graph builder, the docstrings and
#: the Phase 2 exit-criterion test all read from the same source — a test that
#: hard-coded its own copy could agree with itself while disagreeing with the
#: graph.
NODE_SEQUENCE: Final = (
    "validate_input",
    "build_context",
    "choose_model",
    "generate_answer",
    "persist",
)


def build_chat_graph() -> StateGraph[ChatState, None, ChatState, ChatState]:
    """Assemble the graph. Compilation (and the checkpointer) is the caller's."""
    graph: StateGraph[ChatState, None, ChatState, ChatState] = StateGraph(ChatState)
    graph.add_node("validate_input", validate_input)
    graph.add_node("build_context", build_context)
    graph.add_node("choose_model", choose_model)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("persist", persist)

    # A straight line, edge by edge. `add_sequence` would express the same shape
    # in one call, but the explicit edges are what a reader compares against
    # docs/SPEC.md's diagram — and Phase 4 inserts nodes into the middle of this
    # chain, which is easier to review as edges than as a list.
    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "build_context")
    graph.add_edge("build_context", "choose_model")
    graph.add_edge("choose_model", "generate_answer")
    graph.add_edge("generate_answer", "persist")
    graph.add_edge("persist", END)
    return graph
