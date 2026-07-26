"""Typed request and response for a model call.

CLAUDE.md invariant #4: every structured model output is parsed through a
Pydantic schema before it touches persistence or a response. This module is where
that begins — `CompletionResponse.from_provider` is the only way a provider
payload becomes something the rest of the application can use, and it either
produces a valid object or raises.

The response deliberately keeps more than the answer text. Token counts and the
model that actually served the request are what Phase 5's `model_run` table
records; capturing them at the boundary now means observability is a matter of
persisting fields that already exist, rather than re-plumbing the call path.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from ai_core.models.aliases import ModelAlias

# `system` is included because a persisted conversation replays exactly what the
# model was sent (see database.models.conversation.MessageRole) — a prompt change
# must not retroactively rewrite what the model actually saw.
TurnRole = Literal["system", "user", "assistant"]


class ChatTurn(BaseModel):
    """One message in the context sent to a model.

    Not the same type as `database.models.Message`, on purpose. That one is a
    persisted row with an id, a position and a timestamp; this is a wire-format
    turn. Collapsing them would make the working context (which is *assembled*
    per request — docs/ARCHITECTURE.md §6) look like the transcript, which is the
    exact confusion the three memory layers exist to prevent.
    """

    model_config = ConfigDict(frozen=True)

    role: TurnRole
    content: str = Field(min_length=1)


class CompletionRequest(BaseModel):
    """Everything needed to ask a model for an answer."""

    model_config = ConfigDict(frozen=True)

    alias: ModelAlias
    messages: list[ChatTurn] = Field(min_length=1)

    # A ceiling so a runaway generation fails visibly instead of quietly costing
    # money. Not a target — models stop when they are done.
    max_tokens: int = Field(default=1024, gt=0, le=32_000)

    # Deliberately no `temperature`. Reasoning-tier models reject it outright, and
    # the gateway runs with `drop_params: false` so a rejected parameter is an
    # error rather than a silent no-op. Omitting it keeps this request portable
    # across every model an alias might point at; if a phase ever needs sampling
    # control, it should arrive with a reason and a test.


class CompletionResponse(BaseModel):
    """A validated model answer.

    Nothing reaches persistence or an HTTP response without passing through here.
    """

    model_config = ConfigDict(frozen=True)

    #: The alias that was requested — the role, not the model.
    alias: ModelAlias
    #: What actually served it, e.g. `gpt-4o-mini-2024-07-18`. Recorded because
    #: "which model produced this answer" is unanswerable later otherwise: the
    #: alias mapping changes over time, so the alias alone does not identify it.
    provider_model: str
    text: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    #: `stop` on a normal completion; `length` when `max_tokens` was hit, which
    #: means the answer is truncated and callers should not treat it as complete.
    finish_reason: str

    @property
    def was_truncated(self) -> bool:
        """True when the model hit the token ceiling rather than finishing.

        Worth checking before persisting an answer: a truncated summary that
        becomes an approved Learning is a silently corrupted one.
        """
        return self.finish_reason == "length"

    @classmethod
    def from_provider(cls, alias: ModelAlias, payload: Any) -> Self:
        """Validate a raw provider response into this schema.

        Written against the OpenAI-compatible response shape that the LiteLLM
        proxy returns for every provider. Takes `Any` because the SDK's own
        response object is what arrives — the point of this method is that
        nothing downstream ever touches that object, so its type stops here.

        Every field is required. If a provider ever returns a response without
        usage or without a choice, that is a broken response and it should raise
        here rather than become a `CompletionResponse` with silent zeros — token
        counts that are quietly wrong are worse than a loud failure, because
        Phase 5 bills and Phase 6 evaluates on them.
        """
        choice = payload.choices[0]
        usage = payload.usage
        if usage is None:  # pragma: no cover - defensive; the proxy always sends it
            raise ValueError(f"{alias}: provider returned no usage block")
        return cls(
            alias=alias,
            provider_model=payload.model,
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            finish_reason=choice.finish_reason,
        )
