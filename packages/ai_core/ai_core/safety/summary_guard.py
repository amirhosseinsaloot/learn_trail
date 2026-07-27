"""Running the layer-4 validators over a generated summary.

One entry point, `check_summary`, so the graph node stays a graph node and the
validator wiring lives here.

**Which fields are checked, and why not all of them.** The validators compare
prose against the source conversation, so they run over the narrative fields —
`overview`, `key_concepts`, `distinctions`, `examples`, `open_questions`,
`uncertainty_notes`. `title` is excluded because it is deliberately terse and
would fail a vocabulary-overlap check for being short; `suggested_tags` is
excluded because tags are *supposed* to be words the conversation never used
("databases" for a conversation that only ever said "Postgres").

A failure here is not a crash. It is a reason a draft should not be offered for
approval as-is, which the caller turns into a retry or a warning — see
`SummaryCheck.passed`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from guardrails.validator_base import FailResult

from ai_core.safety.summary_validators import (
    TRANSCRIPT_KEY,
    GroundedInTranscript,
    PreservesUncertainty,
)
from ai_core.schemas.summary import LearningSummary


@dataclass(frozen=True)
class SummaryCheck:
    """The outcome of validating one summary."""

    #: Human-readable reasons the summary was rejected. Empty means it passed.
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def __str__(self) -> str:
        return "; ".join(self.failures)


def narrative_text(summary: LearningSummary) -> str:
    """The parts of a summary that make claims about the conversation.

    Joined into one string because the validators reason about vocabulary and
    hedging across the whole summary — a hedge in `uncertainty_notes` legitimately
    covers a confident sentence in `overview`, and checking fields separately
    would report that as a failure.
    """
    parts = [
        summary.overview,
        *summary.key_concepts,
        *summary.distinctions,
        *summary.examples,
        *summary.open_questions,
        *summary.uncertainty_notes,
    ]
    return "\n".join(parts)


def check_summary(summary: LearningSummary, transcript: str) -> SummaryCheck:
    """Run every layer-4 validator, collecting all failures rather than the first.

    All of them, deliberately: a user who fixes one problem and is then told
    about a second has been made to do the work twice, and a regeneration that
    trips a different validator each time looks like the system is guessing.
    """
    text = narrative_text(summary)
    metadata = {TRANSCRIPT_KEY: transcript}

    failures: list[str] = []
    for validator in (PreservesUncertainty(), GroundedInTranscript()):
        result = validator.validate(text, metadata)
        if isinstance(result, FailResult):
            failures.append(result.error_message)

    return SummaryCheck(failures=failures)
