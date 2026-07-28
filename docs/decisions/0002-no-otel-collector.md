# 0002- Export OTLP straight to Phoenix; no standalone collector

Status: Accepted

## Context

Phase 5 introduces tracing. Two of the project's own documents disagree about what
that requires:

- `plans/phase-5.md` task 1 says "Deploy Phoenix **and an OTel collector** in
  docker-compose.yml", and docker-compose.yml's header comment reserved a Phase 5
  slot for "Phoenix + OTel collector".
- docs/SPEC.md §6's service list names PostgreSQL, backend, frontend, **Phoenix**,
  LiteLLM Proxy and an optional local model runtime. No collector.

The disagreement matters because `tests/phases/test_phase_0.py` asserts the compose
service list by **set equality**, so the choice is not a detail that can be deferred:
it is one service or two, decided now.

SPEC §11 states the actual requirement — "keep your instrumentation vendor-neutral"
— and it is worth being precise about where that property comes from. Vendor
neutrality is a property of the *instrumentation*: the application emits OpenTelemetry
spans and exports them over OTLP, reading only the standard `OTEL_*` environment
variables. A collector does not create that property, and its absence does not remove
it. Phoenix accepts OTLP over HTTP natively, so with vendor-neutral instrumentation
the backend can be swapped by changing `OTEL_EXPORTER_OTLP_ENDPOINT` and nothing else.

## Decision

The application exports OTLP directly to Phoenix. No standalone collector service in
Phase 5.

Concretely: the backend reads `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_SERVICE_NAME`
and nothing Phoenix-specific. `arize-phoenix-otel` is deliberately **not** a
dependency — the OTel SDK and the OTLP HTTP exporter are, so no line of Python names
the backend. Compose defines five services, matching SPEC §6 exactly, and
`PHASE_0_SERVICES` is widened by one in the same commit.

## Rejected alternatives

- **Phoenix plus a collector (six services)** — a collector earns its place by doing
  something: fan-out to several backends, tail sampling, redaction, or buffering
  across an application restart. In Phase 5 it would do none of those; it would
  receive spans on one port and forward them to another container. That is a service
  to run, health-check, version and explain, bought with no capability. It also
  contradicts SPEC §6's explicit list, and the SPEC is the more authoritative of the
  two documents in conflict.

- **`arize-phoenix-otel` as the setup path** — it is a genuinely convenient wrapper
  (one `register()` call) and it is exactly the wrong dependency for this decision.
  It would put the backend's name in the application's source, which is the coupling
  the whole "vendor-neutral" instruction exists to prevent. The wrapper saves roughly
  fifteen lines of SDK setup, once.

## Revisit if

Phase 5's deferred Langfuse comparison happens, or a second trace consumer appears.
Fan-out to two backends is the collector's first real job, and at that point adding it
is a compose change plus one environment variable — the instrumentation does not move,
which is the point of having kept it vendor-neutral.

Also revisit if span volume grows enough that dropping spans on a Phoenix restart
starts costing real information. The direct exporter buffers in-process and gives up;
a collector would hold them.
