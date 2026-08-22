"""Running the cloud-vs-local benchmark (docs/SPEC.md §15, Phase 11).

Separate from `benchmark`, which holds the dataset and the report shape and needs
no gateway — so those stay unit-testable while this, the part that calls models,
is the only thing that needs the stack up.

The local side is skipped gracefully when `learning-local` is unreachable: a
machine with no Ollama should still be able to run the cloud half and record a
report that says, honestly, that local was not served. `served=False` is that
statement — it is not a failure, it is the absence of a local runtime.
"""

from __future__ import annotations

import asyncio
from time import perf_counter

from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import GatewayError
from ai_core.models.gateway import answer as ask_model
from ai_core.models.pricing import estimate_cost
from evals.benchmark import (
    CLOUD_ALIAS,
    LOCAL_ALIAS,
    BenchmarkCase,
    BenchmarkReport,
    SideResult,
    coverage,
    load_cases,
)

#: A generous ceiling: a small local model on CPU is slow, and a benchmark that
#: timed it out would measure the timeout rather than the model.
PER_CALL_TIMEOUT_S = 180.0


async def _run_side(alias: ModelAlias, cases: tuple[BenchmarkCase, ...]) -> SideResult:
    latencies: list[float] = []
    coverages: list[float] = []
    cost = 0.0
    served = True

    for case in cases:
        started = perf_counter()
        try:
            async with asyncio.timeout(PER_CALL_TIMEOUT_S):
                response = await ask_model(alias, case.question, max_tokens=400)
        except (GatewayError, TimeoutError):
            # One unreachable call condemns the side: a partial average would
            # flatter whichever model happened to answer the easy prompts.
            served = False
            break

        latencies.append((perf_counter() - started) * 1000)
        coverages.append(coverage(case, response.text))
        priced = estimate_cost(
            response.provider_model, response.input_tokens, response.output_tokens
        )
        cost += float(priced) if priced is not None else 0.0

    if not served or not latencies:
        return SideResult(
            alias=alias.value,
            served=False,
            cases=0,
            avg_latency_ms=0.0,
            avg_coverage=0.0,
            total_cost_usd=0.0,
        )
    return SideResult(
        alias=alias.value,
        served=True,
        cases=len(latencies),
        avg_latency_ms=sum(latencies) / len(latencies),
        avg_coverage=sum(coverages) / len(coverages),
        total_cost_usd=cost,
    )


async def run_benchmark() -> BenchmarkReport:
    """Run both sides over the benchmark set and assemble the report."""
    cases = load_cases()
    cloud = await _run_side(CLOUD_ALIAS, cases)
    local = await _run_side(LOCAL_ALIAS, cases)

    notes: list[str] = []
    if not local.served:
        notes.append(
            "local model was not served — is Ollama running and the model pulled? "
            "The cloud figures stand; the comparison does not."
        )
    elif cloud.served:
        # A one-line, honest summary of the trade the numbers describe.
        faster = "local" if local.avg_latency_ms < cloud.avg_latency_ms else "cloud"
        notes.append(
            f"{faster} was faster on average; local cost ${local.total_cost_usd:.4f} "
            f"against cloud ${cloud.total_cost_usd:.4f}; coverage "
            f"{local.avg_coverage:.2f} local vs {cloud.avg_coverage:.2f} cloud."
        )
    return BenchmarkReport(cloud=cloud, local=local, notes=notes)
