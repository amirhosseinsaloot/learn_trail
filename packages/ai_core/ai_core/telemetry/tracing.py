"""Turning tracing on, and getting a tracer (docs/SPEC.md §11).

**Nothing here names Phoenix.** The exporter reads `OTEL_EXPORTER_OTLP_ENDPOINT`
and `OTEL_SERVICE_NAME`, which are the standard OpenTelemetry variables, so the
backend is chosen in docker-compose.yml and nowhere else
(docs/decisions/0002-no-otel-collector.md). `arize-phoenix-otel` would have made
this file three lines shorter and would have put the vendor's name in it.

**Tracing must never be able to break the product.** Two properties enforce that,
and both are deliberate:

- If no endpoint is configured, spans are still *created* — they just go nowhere.
  Instrumentation that disappeared without a collector would mean the phase test
  could only pass with a running Phoenix, and the graph would behave differently
  in test and in production, which is the opposite of what observability is for.
- Export happens on a background thread through `BatchSpanProcessor`, which
  swallows its own failures. A dead collector costs dropped spans, not a failed
  request. This is the same fail-open reasoning the safety rails use, for the
  same reason.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Final

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span

#: Standard OTel variables. Named rather than inlined so the one place they are
#: read is greppable — and so the phase test can assert nothing else is.
ENDPOINT_ENV_VAR: Final = "OTEL_EXPORTER_OTLP_ENDPOINT"
SERVICE_NAME_ENV_VAR: Final = "OTEL_SERVICE_NAME"
DEFAULT_SERVICE_NAME: Final = "learntrail-api"

#: The instrumentation scope every span in this repo is created under. A trace
#: viewer groups by it, so one name means "our spans" is answerable.
INSTRUMENTATION_SCOPE: Final = "learntrail"

_configured = False


def configure_tracing(*, exporter: Any | None = None) -> TracerProvider | None:
    """Install the global tracer provider. Idempotent; safe to call at startup.

    Returns the provider it installed, or `None` if one was already in place —
    OpenTelemetry's global provider can only be set once per process, and calling
    twice logs a warning and silently keeps the first. Reporting that rather than
    pretending is what stops a test from wondering why its exporter is empty.

    `exporter` is for tests: an `InMemorySpanExporter` makes the whole trace
    assertable with no network and no Phoenix, which is what lets the Phase 5
    exit criterion run on every `make status`.
    """
    global _configured
    if _configured:
        return None

    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": os.environ.get(SERVICE_NAME_ENV_VAR) or DEFAULT_SERVICE_NAME}
        )
    )

    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    elif endpoint := os.environ.get(ENDPOINT_ENV_VAR):
        # OTLP/HTTP wants the full signal path; the variable holds the base.
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
        )
    # else: no processor. Spans are created and dropped — see the module
    # docstring on why that is better than not creating them.

    trace.set_tracer_provider(provider)
    _configured = True
    return provider


def reset_tracing_for_tests() -> None:
    """Forget that `configure_tracing` ran.

    Only for tests, and named so it cannot be mistaken for anything else. The
    global provider itself is not reset — OpenTelemetry does not support that —
    so a test that needs its own exporter must be the first to configure.
    """
    global _configured
    _configured = False


@contextmanager
def capture_spans() -> Iterator[list[ReadableSpan]]:
    """Collect every span finished inside the block, for assertions.

    Lives beside `reset_tracing_for_tests` and for the same reason: the Phase 5
    exit criterion is "a poor answer can be traced through context construction,
    model execution, guardrails and persistence", and the only way to assert that
    without a running Phoenix is to read the spans in-process.

    It *adds* a processor to whatever provider is already installed rather than
    building its own. OpenTelemetry allows the global provider to be set exactly
    once per process, and `api.main` sets it at import — so a test that wanted
    its own provider would silently capture nothing.

    `SimpleSpanProcessor`, not `Batch`: batching is right in production and wrong
    here, where the assertion runs microseconds after the span ends and a
    background flush would make the test a race.
    """
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):  # pragma: no cover - defensive
        raise RuntimeError("no SDK tracer provider is installed; call configure_tracing() first")

    provider.add_span_processor(processor)
    collected: list[ReadableSpan] = []
    try:
        yield collected
    finally:
        processor.force_flush()
        collected.extend(exporter.get_finished_spans())
        # Not removed: the SDK offers no public way to detach a processor. It is
        # shut down instead, which stops it recording — a leaked *live* processor
        # would make every later test in the process slower and its exporter grow
        # without bound.
        processor.shutdown()


def tracer() -> trace.Tracer:
    """The one tracer this repo emits from."""
    return trace.get_tracer(INSTRUMENTATION_SCOPE)


@contextmanager
def span(name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[Span]:
    """Record one operation.

    A thin wrapper over `start_as_current_span`, for two things: the attribute
    helper below (which drops `None` rather than writing the string "None"), and
    one name to change if span creation ever needs a policy.

    **There is deliberately no exception handler here.** An earlier version
    caught, recorded and re-raised — and a mutation test showed removing it
    changed nothing, because `start_as_current_span` defaults
    `record_exception=True` and `set_status_on_exception=True`. A failed call
    already ends up with an `ERROR` status and the exception attached, which is
    what matters: a trace where a failure looks successful misleads the person
    debugging. Left as a comment because the handler looks conspicuously missing
    and someone will otherwise put it back.
    """
    with tracer().start_as_current_span(name) as active:
        if attributes:
            set_attributes(active, attributes)
        yield active


def start_span(name: str, attributes: Mapping[str, Any] | None = None) -> Span:
    """Begin a span **without** making it current, and without ending it.

    For one case, which the plain `span()` context manager genuinely cannot
    cover: an operation that starts in a request handler and finishes inside the
    streaming response body. `POST /chats/{id}/answer` is exactly that shape — it
    loads the conversation, returns a `StreamingResponse`, and only then runs the
    graph — so a `with` block around the handler would close the span before the
    work it is supposed to measure had started.

    The caller activates it in each place with `activate()`, and ends it once.
    """
    started = tracer().start_span(name)
    if attributes:
        set_attributes(started, attributes)
    return started


@contextmanager
def activate(target: Span, *, end: bool = False) -> Iterator[Span]:
    """Make an existing span current for this block; optionally end it after.

    The companion to `start_span`. Spans opened inside the block become its
    children, which is what keeps a trace the shape docs/SPEC.md §11 draws even
    when the parent's lifetime crosses a generator boundary.
    """
    with trace.use_span(
        target, end_on_exit=end, record_exception=True, set_status_on_exception=True
    ):
        yield target


def set_attributes(target: Span, attributes: Mapping[str, Any]) -> None:
    """Attach attributes, skipping the ones that are not yet known.

    `None` is dropped rather than stringified: OTel has no null, so a `None` would
    arrive in the viewer as the literal text "None" and read as a recorded fact
    rather than as an absence.
    """
    for key, value in attributes.items():
        if value is not None:
            target.set_attribute(key, value)


def current_trace_id() -> str | None:
    """The active trace as a 32-character hex string, or `None` if untraced.

    This is what makes the criterion's "traced through" reachable from outside
    the trace: it goes on `model_run.trace_id`, so a row in the database can be
    followed to the trace that produced it — and back, since the UI builds a
    Phoenix link from the same value.

    Formatted here rather than at each call site because OTel exposes it as a
    128-bit int, and the viewer wants zero-padded hex; two call sites formatting
    it by hand is two chances to lose a leading zero.
    """
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return f"{context.trace_id:032x}"
