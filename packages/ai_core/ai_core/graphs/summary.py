"""The summary workflow as a LangGraph graph (docs/SPEC.md §7, Phase 3).

    load_chat -> prepare_context -> generate_summary -> validate_summary
              -> store_draft -> await_approval (interrupt) -> apply_decision

**The node order is the Phase 3 exit criterion.** "Malformed or incomplete
summaries are rejected before persistence" is enforced by where `store_draft`
sits: validation is the node before it, and a failing validation raises rather
than returning, so persistence is never reached. That is a structural guarantee,
not a convention someone has to remember — and the phase test asserts the order.

Validation happens in two layers, and both run before storage:

- **Shape** — Pydantic, inside `generate_summary`. Missing fields, blank entries,
  runaway lists, unknown keys (docs/SPEC.md §8 layer 5).
- **Substance** — Guardrails validators, in `validate_summary`. Did the summary
  preserve the conversation's uncertainty, and does it talk about what was
  actually discussed (layer 4). These need the source, so they cannot be a
  schema.

**`await_approval` is where invariant #5 lives.** The graph stops there and does
not continue until a human supplies a decision. There is no path through this
graph in which a model's output becomes a Learning on its own — the node that
promotes runs only on a resume value the graph cannot produce for itself.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from itertools import pairwise
from typing import Any, Final

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from ai_core.agents.summariser import GeneratedSummary, summarise
from ai_core.safety.summary_guard import check_summary
from ai_core.schemas.summary import LearningSummary

#: Injected on the run config, like the chat graph's persistence callable. The
#: graph knows there is a conversation to load, a draft to store and a decision
#: to apply; it does not know what a database is.
LOAD_TRANSCRIPT_KEY: Final = "load_transcript"
STORE_DRAFT_KEY: Final = "store_draft"
APPLY_DECISION_KEY: Final = "apply_decision"

#: Given a chat id, return its conversation as turns.
LoadTranscript = Callable[[str], Awaitable[list[tuple[str, str]]]]
#: Given a validated summary and its provenance, store it as a draft; return its id.
StoreDraft = Callable[[GeneratedSummary], Awaitable[str]]
#: Given a draft id and the human's decision, act on it; return what happened.
ApplyDecision = Callable[[str, "ReviewDecision"], Awaitable[str]]


class ReviewDecision(StrEnum):
    """What the human chose (docs/SPEC.md §7).

    `EDIT` is deliberately absent. Editing a draft is not a graph decision — it
    is a series of changes the user makes over time through the draft endpoints,
    after which they approve. Modelling it as a resume value would mean holding
    a graph run open across an editing session, which is a worse fit than
    letting the draft simply sit in the database being edited.
    """

    APPROVE = "approve"
    REJECT = "reject"
    REGENERATE = "regenerate"


class SummaryError(RuntimeError):
    """The summary workflow could not complete."""


class SummaryRejected(SummaryError):
    """The generated summary failed validation and was not persisted.

    The exit criterion's failure path, named so a caller can distinguish it from
    a transport failure: this one means the model produced something, and it was
    refused.
    """


class SummaryState(BaseModel):
    """What the summary workflow carries between nodes."""

    chat_id: str

    #: Raw conversation turns, `(role, content)`, as loaded.
    transcript: list[tuple[str, str]] = Field(default_factory=list)

    #: The conversation formatted for the prompt — `prepare_context`'s output,
    #: and also what the layer-4 validators compare the summary against.
    context: str = ""

    summary: LearningSummary | None = None
    prompt_version: str | None = None

    #: Set by `store_draft`. Its presence is the evidence that validation passed,
    #: since nothing else in the graph writes it.
    draft_id: str | None = None

    #: Set by `apply_decision` once a human has chosen.
    decision: ReviewDecision | None = None
    outcome: str | None = None


def _injected(config: RunnableConfig, key: str) -> Any:
    configurable: dict[str, Any] = config.get("configurable") or {}
    value = configurable.get(key)
    if value is None:
        raise SummaryError(f"no {key!r} in the run config; the summary graph cannot proceed")
    return value


async def load_chat(state: SummaryState, config: RunnableConfig) -> dict[str, Any]:
    """Fetch the conversation to be summarised."""
    load: LoadTranscript = _injected(config, LOAD_TRANSCRIPT_KEY)
    transcript = await load(state.chat_id)
    if not transcript:
        raise SummaryError(f"chat {state.chat_id} has no messages to summarise")
    return {"transcript": transcript}


async def prepare_context(state: SummaryState) -> dict[str, Any]:
    """Format the conversation for the prompt.

    Plain `role: content` lines rather than JSON: the model reads this as a
    conversation, and JSON would spend tokens on syntax while making the turn
    structure harder to follow, not easier.

    Unlike the chat graph's `build_context`, this deliberately uses the *whole*
    conversation. A summary of a truncated transcript is a summary of something
    the user did not have — and unlike a chat answer, it is about to become
    durable knowledge.
    """
    return {"context": "\n".join(f"{role}: {content}" for role, content in state.transcript)}


async def generate_summary(state: SummaryState) -> dict[str, Any]:
    """Typed generation via Pydantic AI. Shape validation happens here."""
    generated = await summarise(state.context)
    return {"summary": generated.summary, "prompt_version": generated.prompt_version}


async def validate_summary(state: SummaryState) -> dict[str, Any]:
    """Layer-4 checks against the source conversation.

    Raises on failure, which is what makes the exit criterion structural: the
    next node is `store_draft`, and an exception here means it never runs.
    """
    if state.summary is None:  # pragma: no cover - unreachable via the compiled graph
        raise SummaryError("generate_summary did not produce a summary")

    check = check_summary(state.summary, state.context)
    if not check.passed:
        raise SummaryRejected(f"the summary was rejected before persistence: {check}")
    return {}


async def store_draft(state: SummaryState, config: RunnableConfig) -> dict[str, Any]:
    """Persist the draft — reached only by a summary that passed both layers.

    A *draft*, never a Learning. It is model output that a human has not yet seen
    (CLAUDE.md invariant #5), which is why the table it lands in is separate from
    `learning` rather than a flag on it.
    """
    if state.summary is None or state.prompt_version is None:  # pragma: no cover
        raise SummaryError("store_draft reached without a validated summary")

    store: StoreDraft = _injected(config, STORE_DRAFT_KEY)
    draft_id = await store(
        GeneratedSummary(
            summary=state.summary,
            prompt_version=state.prompt_version,
            # Re-derived rather than carried through state: the alias belongs to
            # the prompt version, and reading it from one place keeps them from
            # drifting apart.
            alias=_alias_for(state.prompt_version),
        )
    )
    return {"draft_id": draft_id}


async def await_approval(state: SummaryState) -> dict[str, Any]:
    """Stop, and wait for a human.

    `interrupt()` raises out of the run, checkpointing everything above it. The
    graph resumes only when a caller supplies a decision — which is why this is
    the node that makes CLAUDE.md invariant #5 structural rather than
    aspirational. A model cannot produce a resume value.

    The payload is what the reviewer needs to decide: the draft's id and its
    content. Deliberately not the whole state — the transcript is already on
    screen, and a checkpointed interrupt payload is a place large values sit
    forever.
    """
    decision = interrupt(
        {
            "draft_id": state.draft_id,
            "summary": state.summary.model_dump() if state.summary else None,
            "prompt_version": state.prompt_version,
        }
    )
    return {"decision": ReviewDecision(decision)}


async def apply_decision(state: SummaryState, config: RunnableConfig) -> dict[str, Any]:
    """Act on what the human chose."""
    if state.draft_id is None or state.decision is None:  # pragma: no cover
        raise SummaryError("apply_decision reached without a draft and a decision")

    apply: ApplyDecision = _injected(config, APPLY_DECISION_KEY)
    return {"outcome": await apply(state.draft_id, state.decision)}


def _alias_for(prompt_version: str) -> Any:
    from ai_core.models.aliases import ModelAlias
    from ai_core.prompt_library import load_active

    name = prompt_version.split("@")[0]
    return ModelAlias(load_active(name).model_settings.alias)


#: The declared order, imported by the phase test rather than copied into it.
#: `store_draft` sitting after `validate_summary` *is* the exit criterion.
NODE_SEQUENCE: Final = (
    "load_chat",
    "prepare_context",
    "generate_summary",
    "validate_summary",
    "store_draft",
    "await_approval",
    "apply_decision",
)


def build_summary_graph() -> StateGraph[SummaryState, None, SummaryState, SummaryState]:
    """Assemble the summary workflow. Compilation is the caller's.

    A checkpointer is **not optional** for this graph, unlike the chat one:
    `interrupt()` needs somewhere to keep the state while a human decides, and
    without one the run cannot be resumed at all.
    """
    graph: StateGraph[SummaryState, None, SummaryState, SummaryState] = StateGraph(SummaryState)
    for name, node in (
        ("load_chat", load_chat),
        ("prepare_context", prepare_context),
        ("generate_summary", generate_summary),
        ("validate_summary", validate_summary),
        ("store_draft", store_draft),
        ("await_approval", await_approval),
        ("apply_decision", apply_decision),
    ):
        graph.add_node(name, node)

    graph.add_edge(START, "load_chat")
    # Built from NODE_SEQUENCE rather than written out, so the declared order and
    # the wired order cannot disagree — the phase test reads that same constant.
    for earlier, later in pairwise(NODE_SEQUENCE):
        graph.add_edge(earlier, later)
    graph.add_edge("apply_decision", END)
    return graph
