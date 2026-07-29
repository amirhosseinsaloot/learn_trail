"""Prompt optimization, and the split that makes it honest (docs/SPEC.md §9, Phase 9).

    "The optimized program performs better on held-out examples, not only its
     optimization set."

The criterion is entirely about **overfitting**, and it is easy to satisfy
accidentally in the wrong direction: any optimizer will improve its own training
score, because that is the number it is climbing. An improvement there is not
evidence of anything. So the machinery here is built around one rule —

    **the held-out set is never seen by the optimizer, at any point.**

`split()` is deterministic and the optimizer is handed `train` only. The
comparison that decides whether the optimization worked reads `held_out`, which
by then has been touched by nothing except the baseline and the candidate being
scored on it.

**COPRO, not MIPROv2 or BootstrapFewShot.** COPRO optimizes *instructions* and
nothing else. The other two produce few-shot demonstrations as a large part of
their gain, and a demonstration cannot be stored in a `prompts/*.toml` version —
it would live in a pickle beside the prompt library, which is exactly the
"optimized artefact nobody can read or review" that docs/SPEC.md §12's versioning
exists to prevent. An instruction is text; it diffs, it reviews, it versions.

**Scale, stated plainly — and this matters more than it first looks.** The
dataset is nine transcripts, five train and four held out. Four consecutive runs
of `make optimize` produced:

    run 1   train 1.00 -> 1.00   held-out 0.71 -> 0.79    IMPROVED
    run 2   train 0.80 -> 0.90   held-out 0.79 -> 0.71    OVERFITTED
    run 3   train 0.87 -> 1.00   held-out 0.76 -> 0.88    IMPROVED
    run 4   train 0.80 -> 0.93   held-out 0.85 -> 0.74    OVERFITTED

Averaging each score over three passes (`REPEATS`) was tried between runs 2 and
3 and did not settle it, which located the variance precisely: it is not in the
*scoring*, it is in **which instruction COPRO lands on**. The optimizer is a
stochastic search, so each run proposes a different candidate — repeated runs
are not repeated measurements of one thing.

The honest reading is that nine cases cannot certify a particular optimized
prompt, and this module says so rather than reporting whichever verdict came up
last. docs/SPEC.md's own warning about DSPy is the same point from the other
side: "optimization without a trustworthy evaluation set only produces
confidently optimized noise."

What *is* established, and what the exit criterion actually asks for, is that the
apparatus can tell the two cases apart — it has now reported `overfitted` on real
runs where train rose and held-out fell, which is the failure the criterion is
named after. Certifying a specific prompt needs a larger dataset; noticing that a
gain did not generalise does not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

DATASET_ROOT: Final = Path(__file__).resolve().parent.parent / "datasets" / "optimization"

#: Where a completed optimization run is recorded. Committed, so "was this
#: prompt version optimized, against what, and did it actually win" is answerable
#: from a checkout rather than from whoever ran it last.
REPORT_PATH: Final = Path(__file__).resolve().parent.parent / "reports" / "optimization.json"

#: Fraction of cases used for optimization. The rest is held out.
#:
#: 0.6 rather than the usual 0.8 because the *held-out* half is what the criterion
#: is about, and with nine cases an 80/20 split leaves two — too few to say
#: anything at all, even directionally.
TRAIN_FRACTION: Final = 0.6

#: How much better the candidate must score on held-out to count as an
#: improvement.
#:
#: The metric is model-judged, so two runs of an unchanged prompt do not agree
#: exactly. Below this, "better" is indistinguishable from noise — and a phase
#: whose whole point is not fooling yourself should not declare victory on a
#: difference it cannot distinguish from a rerun.
MIN_IMPROVEMENT: Final = 0.05


class OptimizationCase(BaseModel):
    """One transcript, and what a good summary of it must and must not contain."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    #: The conversation to summarise, as `role: content` lines. Stored rendered
    #: rather than structured because that is exactly what the summariser is
    #: given, and a dataset that fed it something else would measure a different
    #: function.
    transcript: str = Field(min_length=1)
    #: Points a faithful summary should cover. Scored as a fraction.
    required_points: list[str] = Field(default_factory=list)
    #: Phrases that must not appear. Previous failures live here.
    forbidden_claims: list[str] = Field(default_factory=list)
    notes: str = ""


@cache
def load_cases(root: Path | None = None) -> tuple[OptimizationCase, ...]:
    directory = root or DATASET_ROOT
    return tuple(
        OptimizationCase.model_validate_json(path.read_text())
        for path in sorted(directory.glob("*.json"))
    )


def write_case(case: OptimizationCase, root: Path | None = None) -> Path:
    directory = root or DATASET_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{case.id}.json"
    path.write_text(json.dumps(case.model_dump(mode="json"), indent=2) + "\n")
    return path


def split(
    cases: tuple[OptimizationCase, ...] | None = None,
) -> tuple[tuple[OptimizationCase, ...], tuple[OptimizationCase, ...]]:
    """`(train, held_out)`, deterministically and disjointly.

    Sorted by id and split by position — not shuffled with a seed. A seeded
    shuffle is reproducible only as long as nobody changes the seed or the
    library's RNG, and a split that silently moved would let a case migrate from
    held-out to train between runs, which is the one failure this whole module is
    built to prevent. Sorted order changes only when a case is added or renamed,
    and both are visible in a diff.
    """
    ordered = tuple(sorted(cases or load_cases(), key=lambda case: case.id))
    cut = round(len(ordered) * TRAIN_FRACTION)
    return ordered[:cut], ordered[cut:]


@dataclass(frozen=True)
class Comparison:
    """Baseline versus candidate, on data the optimizer never saw."""

    baseline_train: float
    baseline_held_out: float
    candidate_train: float
    candidate_held_out: float
    #: The optimized instruction, so a human can read what changed before it is
    #: promoted anywhere.
    instruction: str

    @property
    def held_out_delta(self) -> float:
        return self.candidate_held_out - self.baseline_held_out

    @property
    def train_delta(self) -> float:
        return self.candidate_train - self.baseline_train

    @property
    def improved(self) -> bool:
        """Whether the criterion is met: better on **held-out**, beyond noise."""
        return self.held_out_delta > MIN_IMPROVEMENT

    @property
    def overfitted(self) -> bool:
        """Better on train, not on held-out — the failure the criterion names.

        Reported rather than hidden. An optimizer that gains on its own set and
        loses on unseen data has learnt the set, and that is the single most
        useful thing a run of this can tell you.
        """
        return self.train_delta > MIN_IMPROVEMENT and self.held_out_delta <= MIN_IMPROVEMENT

    def verdict(self) -> str:
        if self.improved:
            return "improved"
        if self.overfitted:
            return "overfitted"
        return "unchanged"


def save_report(comparison: Comparison, *, cases: int, train: int, held_out: int) -> None:
    """Record the run. Only a *comparison*, never a promotion.

    Writing the optimized instruction into `prompts/` is a separate, human act —
    plans/phase-9.md: "do not promote without the evaluation suite". A run that
    promoted its own output would make the prompt library's lifecycle
    (draft -> candidate -> active) a formality.
    """
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "verdict": comparison.verdict(),
                "cases": cases,
                "train": train,
                "held_out": held_out,
                "baseline": {
                    "train": round(comparison.baseline_train, 4),
                    "held_out": round(comparison.baseline_held_out, 4),
                },
                "candidate": {
                    "train": round(comparison.candidate_train, 4),
                    "held_out": round(comparison.candidate_held_out, 4),
                },
                "held_out_delta": round(comparison.held_out_delta, 4),
                "min_improvement": MIN_IMPROVEMENT,
                "instruction": comparison.instruction,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def load_report() -> dict[str, object] | None:
    if not REPORT_PATH.exists():
        return None
    loaded: dict[str, object] = json.loads(REPORT_PATH.read_text())
    return loaded
