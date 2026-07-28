"""Tracing for LearnTrail (docs/SPEC.md §11, Phase 5).

Vendor-neutral by construction: OpenTelemetry spans, OTLP export, standard
`OTEL_*` configuration, OpenInference semantic conventions for the model-specific
attributes. No module in this package names a trace backend
(docs/decisions/0002-no-otel-collector.md).
"""

from ai_core.telemetry.spans import (
    CHAT_REQUEST,
    CONTEXT_BUILDER,
    CRITERION_STAGES,
    INPUT_GUARDRAILS,
    LLM_GENERATE,
    LOAD_CONVERSATION,
    OUTPUT_GUARDRAILS,
    PERSIST_MESSAGE,
    SPAN_FOR_NODE,
    SUMMARY_REQUEST,
    Attr,
)
from ai_core.telemetry.tracing import (
    activate,
    capture_spans,
    configure_tracing,
    current_trace_id,
    reset_tracing_for_tests,
    set_attributes,
    span,
    start_span,
    tracer,
)

__all__ = [
    "CHAT_REQUEST",
    "CONTEXT_BUILDER",
    "CRITERION_STAGES",
    "INPUT_GUARDRAILS",
    "LLM_GENERATE",
    "LOAD_CONVERSATION",
    "OUTPUT_GUARDRAILS",
    "PERSIST_MESSAGE",
    "SPAN_FOR_NODE",
    "SUMMARY_REQUEST",
    "Attr",
    "activate",
    "capture_spans",
    "configure_tracing",
    "current_trace_id",
    "reset_tracing_for_tests",
    "set_attributes",
    "span",
    "start_span",
    "tracer",
]
