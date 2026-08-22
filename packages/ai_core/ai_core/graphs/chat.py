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

import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Annotated, Any, Final

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from opentelemetry.trace import Span, Status, StatusCode
from pydantic import BaseModel, Field

from ai_core.graphs.messages import context_from_langchain
from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import GatewayError, stream
from ai_core.models.pricing import estimate_cost
from ai_core.models.routing import Difficulty, fallback_for, route
from ai_core.prompt_library import load_active
from ai_core.safety.decisions import SafetyOutcome, SafetyStage
from ai_core.safety.pipeline import check_input, check_output
from ai_core.schemas.completion import (
    ChatTurn,
    CompletionRequest,
    CompletionResponse,
    FinalChunk,
    TokenChunk,
)
from ai_core.schemas.model_run import ModelRun, RunStatus
from ai_core.telemetry import Attr, current_trace_id, set_attributes, span
from ai_core.telemetry.spans import SPAN_FOR_NODE

#: Key under which the caller supplies the persistence callable (see module
#: docstring). Injected through `config["configurable"]` — LangGraph's standard
#: channel for per-run values that are not part of graph state.
PERSIST_KEY: Final = "persist_answer"

#: Injected recorder for one model call's cost and latency. Separate again, and
#: for the same kind of reason: the money was spent whether or not an answer
#: reached storage, so this must not be able to ride along with persistence.
RECORD_RUN_KEY: Final = "record_run"

#: Injected recorder for safety decisions. Separate from `PERSIST_KEY` because
#: the two are written at different moments and one survives the other: a blocked
#: interaction persists no message but must still persist its safety events.
RECORD_SAFETY_KEY: Final = "record_safety"

#: The prompt version that governs a chat answer (docs/SPEC.md §12). Named once
#: so the node that picks the alias and the node that sends the system message
#: cannot end up reading different versions.
ANSWER_PROMPT: Final = "learning_answer"

#: Injected flag for privacy/offline mode (Phase 11). When True, `choose_model`
#: routes to the local model and nothing leaves the machine. A plain bool, not a
#: callable: it is a deployment mode set once, not a per-request judgement like
#: the budget. Absent (falsy) by default — the graph is cloud-first unless told
#: otherwise.
LOCAL_ONLY_KEY: Final = "local_only"

#: Injected check for whether this chat's spend window is exhausted (Phase 10).
#: A callable, not a bool, so it is evaluated when routing runs rather than when
#: the request was received — and absent by default, because the graph must run
#: with no database and cost-aware routing is an enhancement, not a precondition.
BUDGET_KEY: Final = "budget_exhausted"

#: How long one generation attempt may take before it is abandoned and the
#: fallback alias is tried (Phase 10). Overridable per-run through
#: `config["configurable"]`, which is what lets the exit-criterion test force a
#: timeout without waiting for one. The default is generous: it is a backstop
#: against a hung provider, not a latency target.
GENERATION_TIMEOUT_KEY: Final = "generation_timeout_s"
DEFAULT_GENERATION_TIMEOUT_S: Final = 90.0

#: Signature of that callable: given the finished answer and the id of the model
#: run that produced it, store it and return the id of the row created. Async
#: because the caller's session is async.
PersistAnswer = Callable[[CompletionResponse, str | None], Awaitable[str]]
#: Given one call's facts, record them and return the row's id. The id comes back
#: because the message that results has to point at it.
RecordRun = Callable[[ModelRun], Awaitable[str]]
#: Given one stage's outcome, store its decisions. Returns nothing — the graph
#: does not depend on the audit trail, but the audit trail must not depend on the
#: graph succeeding either.
RecordSafety = Callable[[SafetyOutcome], Awaitable[None]]
#: Returns True when this chat has spent past its window's ceiling. Async because
#: the answer lives in the database the caller owns.
BudgetExhausted = Callable[[], Awaitable[bool]]


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

    #: How `choose_model` rated the question (Phase 10). Kept on state so a trace
    #: and a caller can see *why* an alias was chosen, not only which — a hard
    #: question answered cheaply because the budget was spent looks identical to a
    #: misrouted one without this.
    difficulty: Difficulty | None = None

    #: Set by `generate_answer` when the chosen alias timed out or errored and the
    #: fallback served the answer instead. The whole point of the phase's exit
    #: criterion, made observable.
    used_fallback: bool = False

    #: Set by `generate_answer`, consumed by `persist`.
    answer: CompletionResponse | None = None

    #: Set by `persist` — evidence the answer reached storage.
    persisted_message_id: str | None = None

    #: Set by `generate_answer` — what the call cost, as a row id. Present even
    #: when the answer is refused, because the tokens were spent regardless.
    model_run_id: str | None = None

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


def _describe_safety(active: Span, outcome: SafetyOutcome) -> None:
    """Put a safety verdict on its span.

    The decision, not the content. Categories say *what kind* of concern was
    found and never what matched it — `find_pii` returns categories for exactly
    this reason, and docs/SPEC.md §11 says not to put sensitive content in
    traces. A span that quoted the API key it found would have copied the secret
    into a third place, after the audit row declined to be the second.
    """
    active.set_attributes(
        {
            Attr.SAFETY_ACTION: outcome.action.value,
            Attr.SAFETY_BLOCKED: outcome.blocks,
            Attr.SAFETY_CATEGORIES: outcome.categories,
        }
    )
    for decision in outcome.decisions:
        # One event per check, so a trace shows that three policies ran and which
        # one objected — the same thing `safety_event` records, visible without
        # leaving the trace.
        active.add_event(
            decision.policy_name,
            {
                Attr.SAFETY_ACTION: decision.action.value,
                Attr.SAFETY_POLICY_VERSION: decision.policy_version,
                Attr.SAFETY_CATEGORIES: decision.categories,
            },
        )


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
    with span(SPAN_FOR_NODE["input_safety_check"], {Attr.CHAT_ID: state.chat_id}) as active:
        outcome = await check_input(question)
        _describe_safety(active, outcome)
    await _record(config, outcome)

    if outcome.blocks or outcome.warnings:
        get_stream_writer()(
            {
                "safety": {
                    "stage": SafetyStage.INPUT.value,
                    "action": outcome.action.value,
                    "categories": outcome.categories,
                    # `notice`, not `explanation`: this fires for warnings too,
                    # and `explanation` deliberately names only blocking reasons.
                    "explanation": outcome.notice,
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
    context = list(state.messages)
    with span(SPAN_FOR_NODE["build_context"]) as active:
        # The count, not the content. The messages are already on the model-call
        # span through OpenInference's conventions, and repeating a transcript on
        # every span would multiply the trace's size to say nothing new.
        active.set_attribute(Attr.CONTEXT_MESSAGES, len(context))
    return {"context": context}


async def choose_model(state: ChatState, config: RunnableConfig) -> dict[str, Any]:
    """Route this request to the cheap or the strong model (Phase 10).

    Still a rule and still a model-free node, so the graph stays deterministic and
    the routing decision stays inspectable: given the question you can say which
    alias it produced and why. `classify_difficulty` reads the last user turn;
    `route` maps its verdict to an alias, dropping to the cheap path when the
    chat's spend window is exhausted (cost-aware routing — a graceful downgrade,
    never a refusal).

    The `learning_answer` prompt still names a default alias, but routing is the
    authority on the chat path now. The two agree on the simple case
    (`learning-fast`); routing is what sends a hard question to `learning-deep`.
    """
    question = state.messages[-1].text if state.messages else ""

    configurable: dict[str, Any] = config.get("configurable") or {}
    budget_check: BudgetExhausted | None = configurable.get(BUDGET_KEY)
    exhausted = await budget_check() if budget_check is not None else False
    local_only = bool(configurable.get(LOCAL_ONLY_KEY, False))

    difficulty, alias = route(question, budget_exhausted=exhausted, local_only=local_only)
    with span("choose_model") as active:
        set_attributes(
            active,
            {
                Attr.MODEL_ALIAS: alias.value,
                "learntrail.routing.difficulty": difficulty.value,
                "learntrail.routing.budget_exhausted": exhausted,
                "learntrail.routing.local_only": local_only,
            },
        )
    return {"alias": alias, "difficulty": difficulty}


async def _stream_once(
    request: CompletionRequest,
    writer: Any,
    active: Span,
    *,
    allow_stream: bool,
) -> tuple[CompletionResponse, int]:
    """One generation attempt. Returns the answer and its latency, or raises.

    `allow_stream` is the fallback's safety catch. Tokens cannot be un-shown, so
    the first attempt streams to the client but a *fallback* attempt does not —
    otherwise a strong model that emitted three tokens before hanging, then a
    fast model that answered fully, would paint two overlapping answers on the
    screen. The fallback still streams internally to assemble the response; it
    just does not forward tokens to the writer. The endpoint learns of the
    fallback and re-reads the persisted answer, which is the real one.

    Raises `GraphError` if the stream ends with no final chunk — a dead
    connection rather than a finished answer.
    """
    started = perf_counter()
    first_token_at: float | None = None
    answer: CompletionResponse | None = None

    async for chunk in stream(request):
        if isinstance(chunk, TokenChunk):
            if first_token_at is None:
                first_token_at = perf_counter()
                active.set_attribute(Attr.FIRST_TOKEN_MS, (first_token_at - started) * 1000)
            if allow_stream:
                writer({"token": chunk.text})
        elif isinstance(chunk, FinalChunk):
            answer = chunk.response

    latency_ms = int((perf_counter() - started) * 1000)
    if answer is None:
        raise GraphError("the model stream ended before it completed")

    # The cost and token counts belong on the model span (docs/SPEC.md §11), and
    # they are set here — inside the attempt — so a fallback attempt records its
    # own numbers on its own span rather than the primary's.
    cost = estimate_cost(answer.provider_model, answer.input_tokens, answer.output_tokens)
    set_attributes(
        active,
        {
            Attr.PROVIDER_MODEL: answer.provider_model,
            Attr.INPUT_TOKENS: answer.input_tokens,
            Attr.OUTPUT_TOKENS: answer.output_tokens,
            Attr.TOTAL_TOKENS: answer.input_tokens + answer.output_tokens,
            Attr.ESTIMATED_COST: float(cost) if cost is not None else None,
        },
    )
    return answer, latency_ms


async def generate_answer(state: ChatState, config: RunnableConfig) -> dict[str, Any]:
    """Call the model through the gateway, with a timeout and a fallback (Phase 10).

    Tokens are emitted on LangGraph's `custom` stream channel via
    `get_stream_writer()` — that is what lets the SSE endpoint stream a graph
    execution rather than receive the answer as one lump.

    **The routed alias is tried first, under a timeout.** If it times out before
    producing anything, or the gateway errors, and a fallback alias exists
    (`learning-deep -> learning-fast`), the fallback is tried once. This is the
    half of the exit criterion that a router without it fails: a slow strong model
    on a hard question would otherwise leave the user with nothing, on exactly the
    request the routing existed to serve.

    A failure *after* tokens have streamed is not recoverable — the client has
    already seen output — so it surfaces as an error, the same boundary Phase 4's
    streaming trade-off documents.
    """
    if state.alias is None:  # pragma: no cover - unreachable via the compiled graph
        raise GraphInputError("choose_model did not run before generate_answer")

    configurable: dict[str, Any] = config.get("configurable") or {}
    record_run: RecordRun | None = configurable.get(RECORD_RUN_KEY)
    timeout_s: float = configurable.get(GENERATION_TIMEOUT_KEY) or DEFAULT_GENERATION_TIMEOUT_S

    writer = get_stream_writer()
    prompt = load_active(ANSWER_PROMPT)
    system = ChatTurn(role="system", content=prompt.template.system.strip())
    turns = context_from_langchain(state.context)

    # The aliases to try, in order: the routed one, then its fallback if any.
    # Only the first is allowed to stream to the client — see `_stream_once`.
    attempts: list[tuple[ModelAlias, bool]] = [(state.alias, True)]
    fallback = fallback_for(state.alias)
    if fallback is not None:
        attempts.append((fallback, False))

    answer: CompletionResponse | None = None
    used_alias: ModelAlias = state.alias
    latency_ms = 0
    used_fallback = False
    streamed = False

    for index, (alias, is_primary) in enumerate(attempts):
        request = CompletionRequest(
            alias=alias,
            messages=[system, *turns],
            max_tokens=prompt.model_settings.max_tokens,
        )
        with span(
            SPAN_FOR_NODE["generate_answer"],
            {Attr.SPAN_KIND: "LLM", Attr.MODEL_ALIAS: alias.value, Attr.CHAT_ID: state.chat_id},
        ) as active:
            try:
                async with asyncio.timeout(timeout_s):
                    answer, latency_ms = await _stream_once(
                        request, writer, active, allow_stream=is_primary and not streamed
                    )
                if is_primary:
                    streamed = True
                used_alias = alias
                used_fallback = not is_primary
                break
            except (TimeoutError, GatewayError) as exc:
                # Mark *this* attempt's span failed, even when a fallback follows.
                # Without the explicit status, a primary failure that fell back
                # left an OK-looking span — a trace that hides the failure it
                # exists to show. Found by the Phase 5 test after routing landed.
                active.record_exception(exc)
                active.set_status(Status(StatusCode.ERROR, str(exc)))
                active.add_event("generation_failed", {Attr.MODEL_ALIAS: alias.value})
                # A failure after anything streamed cannot be papered over with a
                # fallback: the client has already seen tokens from a different
                # model. Only a clean pre-stream failure may fall back.
                is_last = index == len(attempts) - 1
                if streamed or is_last:
                    # The original message is carried through, not just the type,
                    # so the trace and the SSE `error` event say what actually
                    # failed rather than only that something did.
                    raise GraphError(f"{alias.value} failed to answer: {exc}") from exc
                # else: loop to the fallback attempt.

    if answer is None:  # pragma: no cover - the loop either set it or raised
        raise GraphError("no attempt produced an answer")

    cost = estimate_cost(answer.provider_model, answer.input_tokens, answer.output_tokens)

    model_run_id: str | None = None
    if record_run is not None:
        model_run_id = await record_run(
            ModelRun(
                operation="chat.answer",
                trace_id=current_trace_id(),
                alias=used_alias,
                provider_model=answer.provider_model,
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                estimated_cost=cost,
                latency_ms=latency_ms,
                status=RunStatus.OK,
            )
        )

    if answer.is_empty:
        # A model may legitimately return nothing, but an empty assistant turn is
        # not worth storing — it would sit in the transcript as a turn that said
        # nothing, and from Phase 3 the transcript is what a Learning is derived
        # from. Raising here means `persist` never runs.
        raise GraphError("the model returned an empty answer")

    return {
        "answer": answer,
        "messages": [AIMessage(content=answer.text)],
        "model_run_id": model_run_id,
        "used_fallback": used_fallback,
    }


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
    with span(SPAN_FOR_NODE["output_safety_check"], {Attr.CHAT_ID: state.chat_id}) as active:
        outcome = await check_output(question, state.answer.text)
        _describe_safety(active, outcome)
    await _record(config, outcome)

    if outcome.blocks or outcome.warnings:
        get_stream_writer()(
            {
                "safety": {
                    "stage": SafetyStage.OUTPUT.value,
                    "action": outcome.action.value,
                    "categories": outcome.categories,
                    "explanation": outcome.notice,
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
    with span(SPAN_FOR_NODE["persist"], {Attr.CHAT_ID: state.chat_id}) as active:
        message_id = await persist_answer(state.answer, state.model_run_id)
        active.set_attribute(Attr.MESSAGE_ID, message_id)
    return {"persisted_message_id": message_id}


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
