"""Cloud-versus-local benchmark (docs/SPEC.md §15, Phase 11).

The phase's exit criterion has two halves: a request can be served entirely
locally, and a cloud-vs-local benchmark result is recorded. This module is the
second half. It runs the same prompts through two aliases — one cloud, one
local — and records latency and a quality proxy for each, so the trade-off a
local model asks you to accept is a measured number rather than a guess.

**Both sides go through the gateway, by alias** (CLAUDE.md invariant #2). The
local side is not special-cased to hit Ollama directly; it is `learning-local`,
resolved by LiteLLM exactly like `learning-fast`. That is what makes the
comparison fair — same code path, same request shape, only the alias differs —
and it is what lets "served locally" be a property of configuration rather than
of a separate branch nobody else exercises.

**Quality here is deliberately crude.** A local 1B model will lose a judged
quality contest to a frontier cloud model, and dressing that up with a GEval
score would imply a precision the comparison does not have. What the benchmark
measures well is the *operational* trade — latency, and whether the local model
stays on topic at all (keyword coverage of an expected-points rubric, the same
cheap check the optimizer uses). The point is not "is local as good"; it is "here
is exactly what you give up for privacy", stated in numbers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from ai_core.models.aliases import ModelAlias

DATASET_ROOT: Final = Path(__file__).resolve().parent.parent / "datasets" / "benchmark"
REPORT_PATH: Final = Path(__file__).resolve().parent.parent / "reports" / "benchmark.json"

#: The two sides. Cloud is the hot-path alias; local is the Phase 11 one. Named
#: as aliases, never as models — which model backs each is infra's decision.
CLOUD_ALIAS: Final = ModelAlias.LEARNING_FAST
LOCAL_ALIAS: Final = ModelAlias.LEARNING_LOCAL


class BenchmarkCase(BaseModel):
    """One prompt, and the points a competent answer should touch."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    #: Keywords a good answer covers. The quality proxy is the fraction present —
    #: coarse on purpose (see the module docstring).
    expected_points: list[str] = Field(default_factory=list)
    notes: str = ""


@cache
def load_cases(root: Path | None = None) -> tuple[BenchmarkCase, ...]:
    directory = root or DATASET_ROOT
    return tuple(
        BenchmarkCase.model_validate_json(path.read_text())
        for path in sorted(directory.glob("*.json"))
    )


def write_case(case: BenchmarkCase, root: Path | None = None) -> Path:
    directory = root or DATASET_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{case.id}.json"
    path.write_text(json.dumps(case.model_dump(mode="json"), indent=2) + "\n")
    return path


def coverage(case: BenchmarkCase, answer: str) -> float:
    """Fraction of expected points whose keywords appear. In [0, 1]."""
    if not case.expected_points:
        return 1.0
    text = answer.lower()
    covered = 0
    for point in case.expected_points:
        words = [word for word in point.lower().split() if len(word) >= 4]
        if words and sum(word in text for word in words) / len(words) >= 0.6:
            covered += 1
    return covered / len(case.expected_points)


@dataclass(frozen=True)
class SideResult:
    """One alias's aggregate over the benchmark set."""

    alias: str
    #: True only if every case actually produced an answer. A local model that is
    #: not running makes this False, which is how the report distinguishes "local
    #: lost" from "local was never asked".
    served: bool
    cases: int
    avg_latency_ms: float
    avg_coverage: float
    total_cost_usd: float


@dataclass
class BenchmarkReport:
    cloud: SideResult
    local: SideResult
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "cloud": _side_dict(self.cloud),
            "local": _side_dict(self.local),
            "notes": self.notes,
        }


def _side_dict(side: SideResult) -> dict[str, object]:
    return {
        "alias": side.alias,
        "served": side.served,
        "cases": side.cases,
        "avg_latency_ms": round(side.avg_latency_ms, 1),
        "avg_coverage": round(side.avg_coverage, 3),
        "total_cost_usd": round(side.total_cost_usd, 6),
    }


def save_report(report: BenchmarkReport) -> None:
    """Record the run so 'a cloud-vs-local benchmark result is recorded' is a fact.

    Committed, like every other report in this package: the trade-off a
    deployment accepted should be answerable from a checkout, not from whoever
    last ran it.
    """
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def load_report() -> dict[str, object] | None:
    if not REPORT_PATH.exists():
        return None
    loaded: dict[str, object] = json.loads(REPORT_PATH.read_text())
    return loaded
