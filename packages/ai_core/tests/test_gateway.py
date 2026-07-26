"""Contract for the gateway client.

Split in two by cost, which is why the markers matter:

- Configuration and error-translation tests run everywhere, spend nothing, and
  need no gateway.
- One **live** test actually calls a model. It is marked `slow`, so `make test`
  (`-m "not slow and not phase"`) skips it: a suite that spends money on every
  pre-push hook is a suite people disable. Run it deliberately with
  `pytest -m slow`.
"""

from __future__ import annotations

import os

import openai
import pytest

from ai_core.models import gateway
from ai_core.models.aliases import ModelAlias
from ai_core.schemas.completion import ChatTurn, CompletionRequest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_client_cache() -> None:
    """The client is cached per process, so a test that changes the environment
    must not leak a client built from the old one into the next test."""
    gateway.client.cache_clear()


# --- configuration -------------------------------------------------------------


def test_gateway_url_defaults_to_the_compose_service(monkeypatch: pytest.MonkeyPatch) -> None:
    # The default is the compose service name, so local development needs no
    # configuration at all.
    monkeypatch.delenv(gateway.GATEWAY_URL_ENV_VAR, raising=False)
    assert gateway.gateway_url() == "http://litellm:4000"


def test_gateway_url_prefers_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(gateway.GATEWAY_URL_ENV_VAR, "http://elsewhere:9000")
    assert gateway.gateway_url() == "http://elsewhere:9000"


def test_a_missing_gateway_key_does_not_raise_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Misconfiguration should fail at the call, where the error names the
    problem — not at import, far from the cause."""
    monkeypatch.delenv(gateway.GATEWAY_KEY_ENV_VAR, raising=False)
    assert gateway.gateway_key() == "sk-missing-gateway-key"
    assert gateway.client() is not None


def test_the_client_is_cached_so_one_pool_is_shared() -> None:
    assert gateway.client() is gateway.client()


def test_the_client_does_not_retry() -> None:
    """Retry and fallback are the gateway's job (docs/SPEC.md §7).

    A second retry layer here would silently multiply both latency and spend on
    every provider failure, and it would do so invisibly — hence an assertion
    rather than a comment.
    """
    assert gateway.client().max_retries == 0


def test_the_client_points_at_the_gateway_not_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLAUDE.md invariant #3 at the client level: whatever this talks to, it is
    not api.openai.com."""
    monkeypatch.setenv(gateway.GATEWAY_URL_ENV_VAR, "http://litellm:4000")
    assert str(gateway.client().base_url).startswith("http://litellm:4000")


# --- error translation ---------------------------------------------------------


@pytest.mark.anyio
async def test_provider_errors_surface_as_gateway_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Callers must not have to import a provider SDK to catch a failure — that
    is exactly what the gateway boundary exists to prevent."""

    class _FailingCompletions:
        async def create(self, **_: object) -> object:
            raise openai.APIConnectionError(request=None)  # type: ignore[arg-type]

    class _FailingChat:
        completions = _FailingCompletions()

    class _FailingClient:
        chat = _FailingChat()

    monkeypatch.setattr(gateway, "client", _FailingClient)

    request = CompletionRequest(
        alias=ModelAlias.LEARNING_FAST, messages=[ChatTurn(role="user", content="hi")]
    )
    with pytest.raises(gateway.GatewayError, match="learning-fast call failed"):
        await gateway.complete(request)


# --- live ----------------------------------------------------------------------


#: From the host, the gateway is on loopback (docker-compose.yml publishes
#: 127.0.0.1:4000); from inside the compose network it is the service name. The
#: default in `gateway.py` is the in-network one, so a host run needs this.
_HOST_GATEWAY_URL = "http://127.0.0.1:4000"


@pytest.mark.slow
@pytest.mark.anyio
async def test_a_real_call_through_an_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Costs money. Excluded from `make test`; run with `pytest -m slow`.

    Asserts the properties only a real provider can demonstrate: that the alias
    resolves to *some* model, and that usage comes back populated — the numbers
    Phase 5 will bill on.

    Skips rather than fails when the stack is down or no key is configured, the
    same contract as the database-backed tests: `make up` is the fix, and a red
    suite on a laptop with Docker stopped teaches people to ignore red suites.
    """
    monkeypatch.setenv(gateway.GATEWAY_URL_ENV_VAR, _HOST_GATEWAY_URL)
    gateway.client.cache_clear()

    if not os.environ.get(gateway.GATEWAY_KEY_ENV_VAR):
        pytest.skip(
            f"{gateway.GATEWAY_KEY_ENV_VAR} unset — export it (see .env) to run the live test"
        )

    try:
        response = await gateway.answer(
            ModelAlias.LEARNING_FAST, "Reply with exactly: ok", max_tokens=5
        )
    except gateway.GatewayError as exc:
        if "Connection" in str(exc) or "connect" in str(exc):
            pytest.skip(f"gateway unreachable at {_HOST_GATEWAY_URL} — run `make up`")
        raise

    # Not asserting the text: a model is not a pure function, and a test that
    # demands exact wording fails for reasons that have nothing to do with the
    # code under test.
    assert response.alias is ModelAlias.LEARNING_FAST
    assert response.provider_model  # the alias resolved to a real model
    assert response.input_tokens > 0
    assert response.output_tokens > 0
