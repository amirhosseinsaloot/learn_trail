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

    # Sampling control, added in Phase 9 with the reason this field's previous
    # comment asked for.
    #
    # **The reason.** Phase 9's exit criterion is comparative — "the optimized
    # program performs better on held-out examples" — and a comparison needs a
    # reproducible baseline. At the provider's default temperature the *system
    # under test* is a fresh sample each run, so the same configuration scored
    # 0.60 and 1.00 on the same case minutes apart. That is enough noise to hide
    # any improvement an optimizer could plausibly produce, which would make the
    # criterion unmeasurable rather than merely imprecise.
    #
    # **`None` means omit, and that is load-bearing.** Reasoning-tier models
    # reject `temperature` outright, and the gateway runs with
    # `drop_params: false` so a rejected parameter is an error rather than a
    # silent no-op. Defaulting to `None` keeps every existing call byte-identical
    # to what it sent before and keeps the request portable across whatever model
    # an alias points at. Only the evaluation path sets it.
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


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
    def is_empty(self) -> bool:
        """True when the model returned no text at all.

        Distinct from truncation: this is a model that said nothing, which is a
        legitimate provider outcome but never something worth persisting as an
        assistant turn.
        """
        return not self.text.strip()

    @property
    def was_truncated(self) -> bool:
        """True when the model hit the token ceiling rather than finishing.

        Worth checking before persisting an answer: a truncated summary that
        becomes an approved Learning is a silently corrupted one.
        """
        return self.finish_reason == "length"

    @classmethod
    def from_streamed(
        cls,
        alias: ModelAlias,
        *,
        provider_model: str,
        text: str,
        finish_reason: str,
        usage: Any,
    ) -> Self:
        """Assemble the same validated response from a finished stream.

        A streamed call never produces one payload to parse: the text arrives in
        deltas and usage arrives in a final chunk. Reconstructing the *same*
        schema here means the streaming and non-streaming paths converge before
        anything is persisted — a streamed answer is not a second, laxer kind of
        answer.
        """
        if usage is None:
            raise ValueError(
                f"{alias}: stream ended with no usage block — "
                "the request needs stream_options={'include_usage': True}"
            )
        return cls(
            alias=alias,
            provider_model=provider_model,
            text=text,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            finish_reason=finish_reason,
        )

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


class TokenChunk(BaseModel):
    """A fragment of a streaming answer, as it arrives."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["token"] = "token"
    text: str


class FinalChunk(BaseModel):
    """The last thing a stream yields: the assembled, validated answer.

    A stream that ends *without* one of these did not finish — it was cut off.
    That distinction is the reason this is a typed chunk rather than a bare
    string: it lets a caller tell "the model is done" from "the connection
    died", and only one of those should be persisted as an answer.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["final"] = "final"
    response: CompletionResponse


#: Discriminated on `kind`, so a consumer either handles both arms or fails to
#: type-check. A stream of plain strings would have made "did it finish?"
#: unrepresentable.
CompletionChunk = TokenChunk | FinalChunk
