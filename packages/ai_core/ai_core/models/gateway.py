"""The one sanctioned model client (docs/CODE_QUALITY.md, `model-call-bypasses-litellm-gateway`).

This module is the **only** place in the repo permitted to import a provider SDK.
Everything else asks for an alias and gets a validated `CompletionResponse` back;
the Semgrep rule that enforces this excludes exactly this path.

Two things that look like provider details and are not:

- The `openai` package here is an HTTP client for an *OpenAI-compatible endpoint*.
  It points at the LiteLLM proxy, which speaks that wire format no matter which
  provider is configured. Swapping providers is still one line in
  infra/litellm/config.yaml.
- `api_key` is the **LiteLLM proxy key**, not a model-provider credential. It
  authenticates this process to the gateway. The provider credential lives only
  in the gateway's own environment and is never held here — that is CLAUDE.md
  invariant #3, and it is verifiable: `printenv` inside the backend container
  shows no provider key.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Final

import openai
from openai.types.chat import ChatCompletionMessageParam

from ai_core.models.aliases import ModelAlias
from ai_core.schemas.completion import ChatTurn, CompletionRequest, CompletionResponse

#: In-network address of the gateway. The default matches the compose service
#: name, so nothing needs configuring for local development.
GATEWAY_URL_ENV_VAR: Final = "LITELLM_BASE_URL"
DEFAULT_GATEWAY_URL: Final = "http://litellm:4000"

#: The key this process presents *to the proxy*. Not a provider credential.
GATEWAY_KEY_ENV_VAR: Final = "LITELLM_MASTER_KEY"


class GatewayError(RuntimeError):
    """A model call failed.

    One domain error rather than leaking `openai.APIError` subclasses outward:
    callers should not have to import a provider SDK to catch a failure, which is
    precisely what the gateway boundary exists to prevent. The original is
    chained, so the provider's own message survives for debugging.
    """


def gateway_url() -> str:
    """Where the LiteLLM proxy lives."""
    return os.environ.get(GATEWAY_URL_ENV_VAR) or DEFAULT_GATEWAY_URL


def gateway_key() -> str:
    """The proxy key, or a placeholder.

    Falling back rather than raising is deliberate: the gateway is what fails on a
    bad key, with a message that says so. Raising here would turn a
    misconfiguration into an import-time or startup-time crash far from the
    actual call, which is harder to diagnose, not easier.
    """
    return os.environ.get(GATEWAY_KEY_ENV_VAR) or "sk-missing-gateway-key"


@lru_cache(maxsize=1)
def client() -> openai.AsyncOpenAI:
    """The process-wide async client, created on first use.

    Cached so the underlying connection pool is shared; `lru_cache` rather than a
    module-level global so tests can reset it with `client.cache_clear()`.
    Created lazily because building it at import time would read the environment
    before the application has finished configuring it.
    """
    return openai.AsyncOpenAI(
        base_url=f"{gateway_url()}/v1",
        api_key=gateway_key(),
        # The gateway is one hop away on the compose network, so a slow call is
        # the *provider* being slow. Generous enough for a real answer, bounded
        # so a hung request cannot pin a connection indefinitely.
        timeout=120.0,
        # Retries are the gateway's job, not ours: LiteLLM owns provider retry and
        # fallback policy (docs/SPEC.md §7), and a second layer here would
        # silently multiply both latency and spend on every failure.
        max_retries=0,
    )


def _as_wire_message(turn: ChatTurn) -> ChatCompletionMessageParam:
    """Translate one domain turn into the SDK's wire type.

    Spelled out per role rather than built as `{"role": turn.role, ...}` because
    the SDK types each role as a *separate* TypedDict, and a dict comprehension
    produces `dict[str, str]`, which matches none of them. mypy catches that; the
    match statement is what lets it narrow.

    This is also the only place the domain's turn shape meets a vendor type,
    which is the point of confining it to this module.
    """
    match turn.role:
        case "system":
            return {"role": "system", "content": turn.content}
        case "user":
            return {"role": "user", "content": turn.content}
        case "assistant":
            return {"role": "assistant", "content": turn.content}


async def complete(request: CompletionRequest) -> CompletionResponse:
    """Ask a model, by alias, and return a validated answer.

    The whole public surface of this package's model layer. Note what the caller
    never sees: no provider name, no SDK type, no raw dict.
    """
    try:
        payload = await client().chat.completions.create(
            model=request.alias.value,
            messages=[_as_wire_message(turn) for turn in request.messages],
            max_tokens=request.max_tokens,
        )
    except openai.APIError as exc:
        # `from exc` keeps the provider's message and traceback attached.
        raise GatewayError(f"{request.alias} call failed: {exc}") from exc

    return CompletionResponse.from_provider(request.alias, payload)


async def answer(alias: ModelAlias, prompt: str, *, max_tokens: int = 1024) -> CompletionResponse:
    """Convenience for the single-turn case, which is most of Phase 1."""
    return await complete(
        CompletionRequest(
            alias=alias,
            messages=[ChatTurn(role="user", content=prompt)],
            max_tokens=max_tokens,
        )
    )
