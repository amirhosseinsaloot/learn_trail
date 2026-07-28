"""The golden datasets, as typed data (docs/SPEC.md §10).

Cases are JSON on disk rather than Python literals so that a case can be added
by someone who is not editing code, and so a failure found in a trace can be
pasted in as a file. The schema is docs/SPEC.md §10's, validated on load —
CLAUDE.md invariant #4 is about model output, but a malformed evaluation case is
worse than malformed model output: it makes the *measurement* wrong, silently.

**Curated, never harvested.** docs/SPEC.md §10 is explicit that production chats
must not automatically become permanent evaluation cases. Every file here was put
there on purpose, and each says why in its `notes`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

DATASETS_ROOT: Final = Path(__file__).resolve().parent.parent / "datasets"

#: The three suites Phase 6 ships. `retrieval` arrives with Phase 8's search and
#: `adversarial` with Phase 7's red teaming — docs/SPEC.md §10 lists all five,
#: and a directory created before its phase would be an empty promise.
SuiteName = Literal["conversations", "summaries", "safety"]
SUITES: Final[tuple[SuiteName, ...]] = ("conversations", "summaries", "safety")


class Turn(BaseModel):
    """One message in a case's conversation."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class EvaluationCase(BaseModel):
    """One golden case (docs/SPEC.md §10's shape, with `notes` added).

    `grading_notes` and `forbidden_claims` are the two halves of a rubric, and
    both are needed: a case with only positive requirements passes on an answer
    that satisfies them *and* invents three other things, which is the
    hallucination failure the suite exists to catch.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    messages: list[Turn] = Field(min_length=1)

    #: What a good answer must contain. Prose, because these are read by an LLM
    #: judge and by a human reviewing a failure — a structured form would be
    #: harder for both.
    grading_notes: list[str] = Field(default_factory=list)

    #: What a good answer must *not* claim. Previous failures live here: this is
    #: where "the model said X, which is wrong" becomes a permanent regression
    #: test rather than a fixed bug that can come back.
    forbidden_claims: list[str] = Field(default_factory=list)

    tags: list[str] = Field(default_factory=list)

    #: Why this case is in the dataset. Not decoration — docs/SPEC.md §10 says to
    #: curate rather than harvest, and a case nobody can justify is one nobody
    #: will dare delete when it stops earning its place.
    notes: str = ""

    #: For safety cases: what the pipeline is expected to do. `None` for suites
    #: where the question is quality rather than policy.
    expected_action: Literal["allow", "allow_with_warning", "block"] | None = None

    @property
    def question(self) -> str:
        """The last user turn — what is actually being asked."""
        for turn in reversed(self.messages):
            if turn.role == "user":
                return turn.content
        raise ValueError(f"case {self.id} has no user turn to evaluate")


@cache
def load_suite(suite: SuiteName, root: Path | None = None) -> tuple[EvaluationCase, ...]:
    """Every case in one suite, ordered by id.

    Ordered so a run is reproducible and two runs are diffable. Cached because
    the datasets are read repeatedly by parametrised tests and do not change
    within a process.
    """
    directory = (root or DATASETS_ROOT) / suite
    cases = [
        EvaluationCase.model_validate_json(path.read_text())
        for path in sorted(directory.glob("*.json"))
    ]
    ids = [case.id for case in cases]
    if len(set(ids)) != len(ids):
        # A duplicate id would make two results collide in `evaluation_result`,
        # and the second would silently overwrite the first.
        duplicates = sorted({name for name in ids if ids.count(name) > 1})
        raise ValueError(f"duplicate case ids in {suite}: {duplicates}")
    return tuple(cases)


def all_cases(root: Path | None = None) -> Iterator[tuple[SuiteName, EvaluationCase]]:
    """Every case in every suite, suite name attached."""
    for suite in SUITES:
        for case in load_suite(suite, root):
            yield suite, case


def write_case(suite: SuiteName, case: EvaluationCase, root: Path | None = None) -> Path:
    """Add a case to a suite on disk. Used by the seeding CLI, not at run time."""
    directory = (root or DATASETS_ROOT) / suite
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{case.id}.json"
    path.write_text(json.dumps(case.model_dump(mode="json"), indent=2) + "\n")
    return path
