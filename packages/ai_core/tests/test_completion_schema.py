"""Contract for the typed model request/response (CLAUDE.md invariant #4).

No network and no database: these are pure validation rules, and the point of
putting them behind a schema is that they can be checked without a provider.

The provider payloads here are hand-built stand-ins shaped like the
OpenAI-compatible response the LiteLLM proxy returns. They are deliberately
duck-typed rather than SDK objects — `from_provider` takes `Any` precisely so the
SDK's type stops at the gateway boundary, and building real SDK objects here
would test the SDK's constructors instead of our validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import ValidationError

from ai_core.models.aliases import ModelAlias
from ai_core.schemas.completion import ChatTurn, CompletionRequest, CompletionResponse


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class _Message:
    content: str | None


@dataclass
class _Choice:
    message: _Message
    finish_reason: str


@dataclass
class _Payload:
    model: str
    choices: list[_Choice]
    usage: _Usage | None


def _payload(
    text: str | None = "an answer",
    *,
    model: str = "gpt-4o-mini-2024-07-18",
    finish_reason: str = "stop",
    usage: _Usage | None = None,
) -> Any:
    # `usage` defaults via None rather than a `_Usage(11, 7)` literal in the
    # signature: a mutable default is evaluated once at import and shared by every
    # caller, which is a real trap even when — as here — nothing mutates it.
    return _Payload(
        model=model,
        choices=[_Choice(_Message(text), finish_reason)],
        usage=_Usage(11, 7) if usage is None else usage,
    )


#: Explicit sentinel for "this response genuinely has no usage block", since
#: `usage=None` above means "give me the default".
NO_USAGE: Any = _Payload(
    model="gpt-4o-mini-2024-07-18", choices=[_Choice(_Message("hi"), "stop")], usage=None
)


# --- the alias is the contract -------------------------------------------------


def test_alias_values_match_the_gateway_config() -> None:
    """Every alias the application can name must be registered in the gateway.

    These strings are the join between application code and
    infra/litellm/config.yaml: an enum member with no matching `model_name` fails
    at runtime the first time it is used. Read from the config rather than
    hardcoded — a hardcoded list is itself a thing that goes stale, and this one
    had (it never included `learning-embedding`).

    Two directions, both checked:

    - every `ModelAlias` value is a registered `model_name` (no unresolvable
      alias);
    - every registered `model_name` is reachable by the application — as an enum
      member, or as `EMBEDDING_ALIAS`, the one alias addressed by a string
      constant rather than the enum (it is not an answer model, so it never flows
      through `CompletionRequest`).
    """
    import pathlib

    import yaml

    from ai_core.retrieval.embedding import EMBEDDING_ALIAS

    config_path = pathlib.Path(__file__).resolve().parents[3] / "infra/litellm/config.yaml"
    config = yaml.safe_load(config_path.read_text())
    registered = {entry["model_name"] for entry in config["model_list"]}

    enum_values = {alias.value for alias in ModelAlias}
    unresolvable = enum_values - registered
    assert unresolvable == set(), f"aliases not registered in the gateway: {sorted(unresolvable)}"

    unreachable = registered - enum_values - {EMBEDDING_ALIAS}
    assert unreachable == set(), (
        f"model_names registered but not addressable by the application: {sorted(unreachable)}"
    )


def test_a_provider_model_string_is_not_a_valid_alias() -> None:
    """CLAUDE.md invariant #2, as a runtime guard rather than a convention.

    A `str` field would have accepted this silently and sent it to the gateway,
    which would then have tried to resolve `gpt-4o` as an alias and failed with a
    much less obvious error.
    """
    with pytest.raises(ValueError, match="not a valid ModelAlias"):
        ModelAlias("gpt-4o")


# --- request validation --------------------------------------------------------


def test_request_rejects_an_empty_conversation() -> None:
    with pytest.raises(ValidationError):
        CompletionRequest(alias=ModelAlias.LEARNING_FAST, messages=[])


def test_request_rejects_an_empty_turn() -> None:
    with pytest.raises(ValidationError):
        ChatTurn(role="user", content="")


@pytest.mark.parametrize("max_tokens", [0, -1, 999_999])
def test_request_rejects_an_implausible_token_ceiling(max_tokens: int) -> None:
    with pytest.raises(ValidationError):
        CompletionRequest(
            alias=ModelAlias.LEARNING_FAST,
            messages=[ChatTurn(role="user", content="hi")],
            max_tokens=max_tokens,
        )


def test_requests_are_immutable() -> None:
    """Frozen so a request cannot be mutated after it is built — a request that
    changes between validation and dispatch is a request that was never
    validated."""
    request = CompletionRequest(
        alias=ModelAlias.LEARNING_FAST, messages=[ChatTurn(role="user", content="hi")]
    )
    with pytest.raises(ValidationError):
        request.alias = ModelAlias.LEARNING_DEEP  # type: ignore[misc]


# --- response validation -------------------------------------------------------


def test_parses_a_well_formed_provider_response() -> None:
    response = CompletionResponse.from_provider(ModelAlias.LEARNING_FAST, _payload())

    assert response.alias is ModelAlias.LEARNING_FAST
    # The alias says which *role* was asked for; provider_model says what actually
    # answered. Both are kept because the mapping between them changes over time.
    assert response.provider_model == "gpt-4o-mini-2024-07-18"
    assert response.text == "an answer"
    assert (response.input_tokens, response.output_tokens) == (11, 7)
    assert response.was_truncated is False


def test_flags_a_truncated_answer() -> None:
    """`length` means the model hit the ceiling, not that it finished.

    Worth flagging rather than inferring at each call site: from Phase 3 a
    summary becomes an approved Learning, and a truncated one is silently
    corrupted knowledge.
    """
    response = CompletionResponse.from_provider(
        ModelAlias.LEARNING_DEEP, _payload(finish_reason="length")
    )
    assert response.was_truncated is True


def test_tolerates_an_empty_completion() -> None:
    # A model can legitimately return no content (a refusal, a stop sequence hit
    # immediately). That is an empty answer, not a malformed response.
    response = CompletionResponse.from_provider(ModelAlias.LEARNING_FAST, _payload(text=None))
    assert response.text == ""


def test_rejects_a_response_with_no_usage_block() -> None:
    """Loud failure rather than silent zeros.

    Phase 5 bills on these numbers and Phase 6 evaluates on them; a response
    recorded as costing zero tokens is worse than one that failed to parse.
    """
    with pytest.raises(ValueError, match="no usage block"):
        CompletionResponse.from_provider(ModelAlias.LEARNING_FAST, NO_USAGE)


def test_rejects_negative_token_counts() -> None:
    with pytest.raises(ValidationError):
        CompletionResponse.from_provider(ModelAlias.LEARNING_FAST, _payload(usage=_Usage(-1, 5)))


def test_responses_are_immutable() -> None:
    response = CompletionResponse.from_provider(ModelAlias.LEARNING_FAST, _payload())
    with pytest.raises(ValidationError):
        response.text = "rewritten"  # type: ignore[misc]
