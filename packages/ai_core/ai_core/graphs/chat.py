"""The chat workflow as a LangGraph graph (docs/SPEC.md §15, Phase 2).

    validate_input -> input_safety_check -> build_context -> choose_model
                   -> generate_answer -> output_safety_check -> persist

with a refusal edge from each safety check straight to END.

Phase 1 made this same sequence happen inside one endpoint function. Moving it
into a graph is not decoration: each step becomes a named, separately-inspectable
unit, the checkpointer records the state after every one of them, and the Phase 2
exit criterion — "each chat request is visible as a deterministic graph
execution" — becomes something you can assert rather than assume.

**Deterministic** is still the load-bearing word, and Phase 4 narrows rather than
abandons it. The two conditional edges added here are the graph's first, and they
branch on a *recorded decision* — `SafetyOutcome.blocks`, already computed and
already on state — not on a model choosing a route. So the shape stays
inspectable: given a state you can say which edge was taken and why, which is what
the Phase 4 exit criterion ("every model interaction has an explicit, testable
safety path") actually demands. `choose_model` still picks an alias by rule; Phase
10's real routing is a separate, later decision about this same graph.

**The output check runs after tokens have already streamed.** That is a genuine
weakness, taken with open eyes: streaming is the product, and buffering the whole
answer to check it first would cost the thing the user came for. What the graph
guarantees instead is that a blocked answer is *never persisted* and the caller is
told to discard what it showed. Nothing enters the transcript — and therefore
nothing can reach a Learning — without having passed the output check.

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
from ai_core.safety.decisions import SafetyOutcome, SafetyStage
from ai_core.safety.pipeline import check_input, check_output
from ai_core.schemas.completion import CompletionRequest, CompletionResponse, FinalChunk, TokenChunk

#: Key under which the caller supplies the persistence callable (see module
#: docstring). Injected through `config["configurable"]` — LangGraph's standard
#: channel for per-run values that are not part of graph state.
PERSIST_KEY: Final = "persist_answer"

#: Injected recorder for safety decisions. Separate from `PERSIST_KEY` because
#: the two are written at different moments and one survives the other: a blocked
#: interaction persists no message but must still persist its safety events.
RECORD_SAFETY_KEY: Final = "record_safety"

#: Signature of that callable: given the finished answer, store it and return the
#: id of the row created. Async because the caller's session is async.
PersistAnswer = Callable[[CompletionResponse], Awaitable[str]]
#: Given one stage's outcome, store its decisions. Returns nothing — the graph
#: does not depend on the audit trail, but the audit trail must not depend on the
#: graph succeeding either.
RecordSafety = Callable[[SafetyOutcome], Awaitable[None]]


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

    #: What the input and output checks decided. Kept on state rather than being
    #: acted on and discarded, so a caller can report *why* an interaction stopped
    #: and the checkpointed run records the reasoning, not just the result.
    input_safety: SafetyOutcome | None = None
    output_safety: SafetyOutcome | None = None

    #: Which stage refused, if either did.
    blocked_at: SafetyStage | None = None


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


async def _record(config: RunnableConfig, outcome: SafetyOutcome) -> None:
    """Hand an outcome to the caller's recorder, if one was injected.

    Unlike `PERSIST_KEY`, a missing recorder is not an error. The graph must run
    with no database at all (see the module docstring), and refusing to check
    safety because nobody was listening would invert the priority: the check is
    what protects the user, the audit trail is what explains it afterwards.
    """
    configurable: dict[str, Any] = config.get("configurable") or {}
    record_safety: RecordSafety | None = configurable.get(RECORD_SAFETY_KEY)
    if record_safety is not None:
        await record_safety(outcome)


async def input_safety_check(state: ChatState, config: RunnableConfig) -> dict[str, Any]:
    """Judge the question before spending anything on it.

    Placed after `validate_input` and before `build_context` so a blocked request
    costs one cheap-alias judge call and no answer generation. Emits its verdict on
    the `custom` stream because the SSE caller has already opened a response by the
    time this runs and needs to be told why nothing will follow.
    """
    question = state.messages[-1].text if state.messages else ""
    outcome = await check_input(question)
    await _record(config, outcome)

    if outcome.blocks or outcome.warnings:
        get_stream_writer()(
            {
                "safety": {
                    "stage": SafetyStage.INPUT.value,
                    "action": outcome.action.value,
                    "categories": outcome.categories,
                    "explanation": outcome.explanation,
                }
            }
        )
    return {
        "input_safety": outcome,
        "blocked_at": SafetyStage.INPUT if outcome.blocks else None,
    }


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


async def output_safety_check(state: ChatState, config: RunnableConfig) -> dict[str, Any]:
    """Judge the answer before it is allowed to become part of the record.

    It cannot un-show what streamed. What it can do is stop a bad answer from
    entering the transcript, which is the input to every summary and therefore to
    every Learning — so this is the gate that keeps CLAUDE.md invariant #5 from
    being handed poisoned material to approve.

    Told the question as well as the answer, because "is this response
    appropriate" is not answerable about the response alone: a refusal to a benign
    question and a compliance with a malicious one look identical in isolation.
    """
    if state.answer is None:  # pragma: no cover - unreachable via the compiled graph
        raise GraphInputError("generate_answer did not produce an answer")

    question = state.messages[-2].text if len(state.messages) >= 2 else ""
    outcome = await check_output(question, state.answer.text)
    await _record(config, outcome)

    if outcome.blocks or outcome.warnings:
        get_stream_writer()(
            {
                "safety": {
                    "stage": SafetyStage.OUTPUT.value,
                    "action": outcome.action.value,
                    "categories": outcome.categories,
                    "explanation": outcome.explanation,
                    # The caller has already rendered tokens from this answer. It
                    # must be told to drop them, not merely warned.
                    "discard": outcome.blocks,
                }
            }
        )
    return {
        "output_safety": outcome,
        "blocked_at": SafetyStage.OUTPUT if outcome.blocks else None,
    }


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


#: The two branch labels, named so the builder and the tests cannot drift.
BLOCKED: Final = "blocked"
CONTINUE: Final = "continue"


def route_after_safety(state: ChatState) -> str:
    """The one branching rule in this graph: refused stops, anything else goes on.

    A plain function of state, deliberately: the router does no work and makes no
    judgement of its own, so "why did this run stop" is answered entirely by the
    `SafetyOutcome` already recorded — and the routing itself has nothing left in
    it that could be wrong.
    """
    return BLOCKED if state.blocked_at is not None else CONTINUE


#: The node order on the unblocked path, as one list. Named so the graph builder,
#: the docstrings and the exit-criterion tests all read from the same source — a
#: test that hard-coded its own copy could agree with itself while disagreeing
#: with the graph.
NODE_SEQUENCE: Final = (
    "validate_input",
    "input_safety_check",
    "build_context",
    "choose_model",
    "generate_answer",
    "output_safety_check",
    "persist",
)

#: The nodes that may end the run early. Phase 2 had none; keeping the set
#: explicit means a third one cannot be added without saying so here.
BRANCHING_NODES: Final = ("input_safety_check", "output_safety_check")


def build_chat_graph() -> StateGraph[ChatState, None, ChatState, ChatState]:
    """Assemble the graph. Compilation (and the checkpointer) is the caller's."""
    graph: StateGraph[ChatState, None, ChatState, ChatState] = StateGraph(ChatState)
    graph.add_node("validate_input", validate_input)
    graph.add_node("input_safety_check", input_safety_check)
    graph.add_node("build_context", build_context)
    graph.add_node("choose_model", choose_model)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("output_safety_check", output_safety_check)
    graph.add_node("persist", persist)

    # Edge by edge rather than `add_sequence`, because the shape is no longer a
    # sequence: the two conditional edges below are the part of this graph a
    # reader most needs to see, and burying them beside a one-call happy path
    # would hide the only place the workflow can end early.
    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "input_safety_check")
    graph.add_conditional_edges(
        "input_safety_check",
        route_after_safety,
        {CONTINUE: "build_context", BLOCKED: END},
    )
    graph.add_edge("build_context", "choose_model")
    graph.add_edge("choose_model", "generate_answer")
    graph.add_edge("generate_answer", "output_safety_check")
    graph.add_conditional_edges(
        "output_safety_check",
        route_after_safety,
        # BLOCKED skips `persist` entirely. That is the whole enforcement: a
        # refused answer leaves no message row, so nothing downstream — summary,
        # draft, Learning — can ever be built from it.
        {CONTINUE: "persist", BLOCKED: END},
    )
    graph.add_edge("persist", END)
    return graph
