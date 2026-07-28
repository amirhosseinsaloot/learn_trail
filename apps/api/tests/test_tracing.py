"""Contract for the trace a chat request emits (docs/SPEC.md §11, Phase 5).

Runs against the real app and the real graph, with the gateway and the safety
checks stubbed and an in-memory span exporter attached — so the *shape* of the
trace is asserted without a running Phoenix, without a model call and without
anything leaving the process.

What is being tested is not "OpenTelemetry works". It is that the four stages
the Phase 5 exit criterion names are each visible as a named span, that they nest
under one request, and that no span carries content it should not.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import ReadableSpan
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_core.graphs.chat import build_chat_graph
from ai_core.telemetry import Attr, capture_spans
from ai_core.telemetry.spans import (
    CHAT_REQUEST,
    CRITERION_STAGES,
    LLM_GENERATE,
    LOAD_CONVERSATION,
)
from api.main import app
from database.session import engine, session

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(anyio_backend: str) -> AsyncIterator[AsyncClient]:
    from langgraph.checkpoint.memory import InMemorySaver

    try:
        connection = await engine().connect()
    except DBAPIError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no database reachable ({type(exc).__name__}) — run `make up`")

    transaction = await connection.begin()
    test_session = AsyncSession(bind=connection, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield test_session

    app.dependency_overrides[session] = override_session
    app.state.chat_graph = build_chat_graph().compile(checkpointer=InMemorySaver())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://learntrail.test"
        ) as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        await test_session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


@pytest.fixture(autouse=True)
def stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """No model call, at either the answer or the guardrail.

    Both would otherwise reach the gateway: the graph's `generate_answer` and the
    NeMo rails inside `check_input`/`check_output`.
    """
    from ai_core import CompletionResponse, FinalChunk, ModelAlias, TokenChunk
    from ai_core.graphs import chat as chat_module
    from ai_core.safety.decisions import SafetyDecision, SafetyOutcome, SafetyStage

    async def fake_stream(request: object) -> AsyncIterator[object]:
        yield TokenChunk(text="an ")
        yield TokenChunk(text="answer")
        yield FinalChunk(
            response=CompletionResponse(
                alias=ModelAlias.LEARNING_FAST,
                provider_model="stub-model",
                text="an answer",
                input_tokens=11,
                output_tokens=3,
                finish_reason="stop",
            )
        )

    def allowed(stage: SafetyStage) -> SafetyOutcome:
        return SafetyOutcome(
            stage=stage, decisions=[SafetyDecision.allow(stage, "stub_policy", "stub@1")]
        )

    async def fake_input(text: str) -> SafetyOutcome:
        return allowed(SafetyStage.INPUT)

    async def fake_output(question: str, answer: str) -> SafetyOutcome:
        return allowed(SafetyStage.OUTPUT)

    monkeypatch.setattr(chat_module, "stream", fake_stream)
    monkeypatch.setattr(chat_module, "check_input", fake_input)
    monkeypatch.setattr(chat_module, "check_output", fake_output)


async def _answered(client: AsyncClient, question: str = "why?") -> list[ReadableSpan]:
    """Ask a question with span capture on; return the spans it produced."""
    chat_id = (await client.post("/chats", json={"title": "traced"})).json()["id"]
    await client.post(f"/chats/{chat_id}/messages", json={"content": question})
    with capture_spans() as spans:
        await client.post(f"/chats/{chat_id}/answer")
    return spans


def _named(spans: list[ReadableSpan], name: str) -> ReadableSpan:
    matches = [s for s in spans if s.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r}, got {[s.name for s in spans]}"
    return matches[0]


async def test_every_stage_the_criterion_names_is_a_span(client: AsyncClient) -> None:
    """The exit criterion, read literally.

    "Context construction, model execution, guardrails and persistence" — each
    one has to be findable in the trace, or the answer cannot be traced *through*
    it. The stage-to-span mapping is read from `CRITERION_STAGES` rather than
    written out here, so this test and the instrumentation cannot disagree about
    which span means which stage.
    """
    spans = await _answered(client)
    emitted = {span.name for span in spans}
    for stage, required in CRITERION_STAGES.items():
        missing = [name for name in required if name not in emitted]
        assert not missing, f"{stage} is not traceable: {missing} missing from {sorted(emitted)}"


async def test_the_stages_nest_under_one_request(client: AsyncClient) -> None:
    """A flat list of spans is not a trace.

    "Traced *through*" means the stages are connected — one request, whose parts
    are its children. Spans that shared no trace would still each be findable and
    would answer nothing about a particular poor answer.
    """
    spans = await _answered(client)
    request_span = _named(spans, CHAT_REQUEST)

    for stage_spans in CRITERION_STAGES.values():
        for name in stage_spans:
            assert _named(spans, name).context.trace_id == request_span.context.trace_id, name

    # `load_conversation` runs in the handler, the rest inside the streaming
    # body — different call stacks, and the reason `chat.request` is started and
    # activated by hand. If that plumbing broke, this is what would catch it.
    parent = _named(spans, LOAD_CONVERSATION).parent
    assert parent is not None
    assert parent.span_id == request_span.context.span_id


async def test_the_model_span_carries_what_the_answer_cost(client: AsyncClient) -> None:
    """Token counts on the span, not only in the database.

    docs/SPEC.md §11 lists them under "Capture". They are what makes a trace
    answer "was this answer expensive as well as poor" without a second query.
    """
    generate = _named(await _answered(client), LLM_GENERATE)
    attributes = generate.attributes or {}
    assert attributes[Attr.INPUT_TOKENS] == 11
    assert attributes[Attr.OUTPUT_TOKENS] == 3
    assert attributes[Attr.PROVIDER_MODEL] == "stub-model"
    # The alias is the app's vocabulary and the provider model is what served it;
    # a trace that recorded only one of them cannot answer routing questions.
    assert attributes[Attr.MODEL_ALIAS] == "learning-fast"


async def test_first_token_latency_is_recorded(client: AsyncClient) -> None:
    """The number the user actually feels.

    Total latency hides a stream that took four seconds to *start* behind one
    that took four seconds to finish, and those are different problems.
    """
    generate = _named(await _answered(client), LLM_GENERATE)
    # An OTel attribute is a union of every allowed type; narrowing is the price
    # of that, and asserting the type is part of the point — a latency recorded
    # as a string would render as text in the viewer and sort alphabetically.
    latency = (generate.attributes or {})[Attr.FIRST_TOKEN_MS]
    assert isinstance(latency, float)
    assert latency >= 0


async def test_guardrail_spans_record_the_decision_and_not_the_content(
    client: AsyncClient,
) -> None:
    """docs/SPEC.md §11: do not put sensitive content in traces.

    The guardrail spans say what was decided and what kind of concern was found.
    They must not carry the text that was judged — a span quoting the API key it
    detected would have copied the secret into a third place, after the audit row
    deliberately declined to be the second.
    """
    question = "my key is sk-abcdefghijklmnop0123456789"
    spans = await _answered(client, question)

    for name in CRITERION_STAGES["guardrails"]:
        guardrail = _named(spans, name)
        attributes = guardrail.attributes or {}
        assert attributes[Attr.SAFETY_ACTION] == "allow"
        assert attributes[Attr.SAFETY_BLOCKED] is False
        # Every check that ran is an event, so the trace shows which policies
        # spoke, not just what they concluded together.
        assert [event.name for event in guardrail.events] == ["stub_policy"]

    for span in spans:
        for value in (span.attributes or {}).values():
            assert "sk-abcdefghijklmnop" not in str(value), span.name


async def test_a_failed_answer_leaves_an_errored_span(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A trace where a failed request looks successful is worse than no trace.

    This is the case the criterion is actually about — something went wrong and
    you are trying to find out where — so the span has to say so rather than
    ending quietly with an OK status.
    """
    from ai_core import GatewayError, TokenChunk
    from ai_core.graphs import chat as chat_module

    async def dying_stream(request: object) -> AsyncIterator[object]:
        yield TokenChunk(text="half an ")
        # `GatewayError` rather than a bare exception: it is what a real provider
        # failure raises, and it is what the endpoint knows how to turn into an
        # `error` event instead of a dropped connection.
        raise GatewayError("the provider hung up")

    monkeypatch.setattr(chat_module, "stream", dying_stream)
    spans = await _answered(client)

    generate = _named(spans, LLM_GENERATE)
    assert generate.status.is_ok is False
    assert "hung up" in (generate.status.description or "")
