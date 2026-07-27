"""Adapters between LearnTrail's turns and LangChain message objects.

The graph carries `langchain_core` messages in its state rather than our own
`ChatTurn`, for one concrete reason: LangGraph's `add_messages` reducer, the
checkpointer's serialization, and every LangChain integration a later phase might
pull in are all written against `BaseMessage`. Using anything else would mean
re-implementing that reducer and its merge semantics ourselves.

What does *not* change is who talks to a model. LangChain supplies the message
vocabulary here; the actual call still goes through `ai_core.models.gateway` and
therefore through a LiteLLM alias (CLAUDE.md invariant #2). No
`langchain_openai`, no `ChatOpenAI` — a second client would be a second place a
provider gets named, which is exactly what the gateway exists to prevent.

These functions are the boundary. `ChatTurn` stays the type the API layer sees,
so a LangChain upgrade that renames a message class stops here.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from ai_core.schemas.completion import ChatTurn, TurnRole


def to_langchain(turn: ChatTurn) -> BaseMessage:
    """One domain turn as a LangChain message.

    Spelled out per role rather than looked up in a dict: the classes have
    different constructors and mypy can only narrow through explicit branches —
    the same reason `gateway._as_wire_message` is written this way.
    """
    match turn.role:
        case "system":
            return SystemMessage(content=turn.content)
        case "user":
            return HumanMessage(content=turn.content)
        case "assistant":
            return AIMessage(content=turn.content)


def from_langchain(message: BaseMessage) -> ChatTurn:
    """One LangChain message back as a domain turn.

    `message.content` is typed as `str | list[...]` upstream because LangChain
    supports multimodal content blocks. LearnTrail is text-only through Phase 1,
    so a non-string here means something upstream started producing content this
    layer was never designed for — better to fail loudly than to stringify a
    structure and persist the repr.
    """
    if not isinstance(message.content, str):
        raise TypeError(
            f"expected text content, got {type(message.content).__name__}; "
            "multimodal messages are not supported"
        )
    return ChatTurn(role=_role_of(message), content=message.content)


def _role_of(message: BaseMessage) -> TurnRole:
    match message:
        case SystemMessage():
            return "system"
        case HumanMessage():
            return "user"
        case AIMessage():
            return "assistant"
        case _:
            # ToolMessage and friends. They are legitimate LangChain types, just
            # not part of a LearnTrail conversation — tools arrive no earlier
            # than the retrieval work in Phase 8, and would need a `message.role`
            # value and a database enum member before they could be stored.
            raise TypeError(
                f"unsupported message type for a conversation: {type(message).__name__}"
            )


def context_to_langchain(turns: list[ChatTurn]) -> list[BaseMessage]:
    """A whole working context, converted for the graph."""
    return [to_langchain(turn) for turn in turns]


def context_from_langchain(messages: list[BaseMessage]) -> list[ChatTurn]:
    """A whole working context, converted back for the gateway."""
    return [from_langchain(message) for message in messages]
