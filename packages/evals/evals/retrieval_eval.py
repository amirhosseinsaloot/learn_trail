"""Evaluating retrieval, not generation (docs/SPEC.md §9, Phase 8).

**Why this is a separate suite from the golden one.** Phase 6's metrics judge an
*answer*. They cannot distinguish "the model was given the right passages and
wrote a poor answer" from "the model wrote the best answer available from the
wrong passages" — and those need opposite fixes. Retrieval metrics ask about the
passages, which is the only way to tell the two apart.

Three questions, each with a distinct failure behind it:

    context precision   Of what was retrieved, how much was relevant?
                        Low means the answer is being written over noise.
    context recall      Of what the answer needed, how much was retrieved?
                        Low means the library knew and search did not find it —
                        the worst failure, because the answer still looks
                        confident and still carries citations.
    faithfulness        Does the answer stay inside the passages?
                        Low means the model filled a gap from its own knowledge,
                        which is precisely what the citations then misattribute.

**These are Ragas's definitions, implemented here rather than imported.**
docs/SPEC.md §9 names Ragas and that was the intent; ragas 0.4.3 cannot be loaded
in this environment. Every entry point routes through `ragas.llms.base`, which
hard-imports `langchain_community.chat_models.vertexai` — a module that current
`langchain-community` no longer provides:

    ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'

Making it work means pinning a dated `langchain-community` to route around an
upstream bug, and pulling a very large dependency tree into a suite that needs
three prompts. The metrics are well-specified and short, so they are implemented
directly — which also keeps the judge on the LiteLLM gateway, where CLAUDE.md
invariant #2 says every model call belongs. Revisit when ragas fixes the import;
the dataset and thresholds here transfer unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import answer as ask_model

DATASET_ROOT: Final = Path(__file__).resolve().parent.parent / "datasets" / "retrieval"

#: The judge. `safety-judge` for the same reason the golden suite uses it —
#: judging is a cheap-model classification job done many times per run.
JUDGE_ALIAS: Final = ModelAlias.SAFETY_JUDGE

#: Bars for the three metrics. Deliberately not 1.0: every one is judged by a
#: model, so a perfect bar fails on noise, and a suite that fails on noise is one
#: people rerun until it passes.
#:
#: Recall is highest because its failure is the most damaging — a passage that
#: existed and was not retrieved produces a confident answer citing whatever
#: *was* found. Precision is lowest because retrieving a few extra passages is
#: cheap and mostly harmless; the model is asked to use what is relevant.
THRESHOLDS: Final[dict[str, float]] = {
    "context_precision": 0.50,
    "context_recall": 0.70,
    "faithfulness": 0.70,
}


class RetrievalCase(BaseModel):
    """One question, and what a good retrieval would have found.

    `ground_truth` is written by hand: it is what the *library* should be able to
    support, not what the model happens to say. Deriving it from a model's answer
    would make the metric measure the system's agreement with itself.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    ground_truth: str = Field(min_length=1)
    #: Titles of the Learnings that ought to supply it. Checked as a set, with no
    #: judge involved — "did search find the right document" needs no opinion.
    expected_learnings: list[str] = Field(default_factory=list)
    notes: str = ""


@cache
def load_retrieval_cases(root: Path | None = None) -> tuple[RetrievalCase, ...]:
    directory = root or DATASET_ROOT
    return tuple(
        RetrievalCase.model_validate_json(path.read_text())
        for path in sorted(directory.glob("*.json"))
    )


def write_case(case: RetrievalCase, root: Path | None = None) -> Path:
    directory = root or DATASET_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{case.id}.json"
    path.write_text(json.dumps(case.model_dump(mode="json"), indent=2) + "\n")
    return path


@dataclass(frozen=True)
class RetrievalScore:
    """What one case scored, and whether the right documents were found."""

    case_id: str
    metrics: dict[str, float]
    #: Titles actually retrieved. The judge-free half of the measurement, and the
    #: first thing to read when a score looks wrong.
    retrieved_learnings: list[str]
    expected_learnings: list[str]

    @property
    def found_expected(self) -> bool:
        return set(self.expected_learnings) <= set(self.retrieved_learnings)

    @property
    def failures(self) -> list[str]:
        below = [
            f"{name} {value:.2f} < {THRESHOLDS[name]:.2f}"
            for name, value in sorted(self.metrics.items())
            if name in THRESHOLDS and value < THRESHOLDS[name]
        ]
        if not self.found_expected:
            missing = sorted(set(self.expected_learnings) - set(self.retrieved_learnings))
            below.append(f"expected Learnings not retrieved: {missing}")
        return below

    @property
    def passed(self) -> bool:
        return not self.failures


async def _judge_fraction(prompt: str, items: list[str]) -> tuple[float, str]:
    """Ask the judge a yes/no question about each item; return the pass fraction.

    A fraction rather than a single score, because that is what makes these
    metrics readable: "3 of 5 passages were relevant" is actionable, and 0.6 on
    its own is not. The judge answers one line per item, which is far more
    reliable than asking it for a number — models are poor at calibrated scoring
    and good at binary classification.
    """
    if not items:
        # Nothing to judge is not a failure. An empty retrieval is a *recall*
        # problem, and reporting it as zero precision would double-count it.
        return 1.0, "nothing to judge"

    numbered = "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))
    response = await ask_model(
        JUDGE_ALIAS,
        f"{prompt}\n\n{numbered}\n\n"
        f"Answer with exactly {len(items)} lines, one per numbered item, each "
        "either YES or NO and nothing else.",
        max_tokens=200,
    )
    verdicts = [
        line.strip().upper().lstrip("0123456789. ")
        for line in response.text.splitlines()
        if line.strip()
    ]
    yes = sum(1 for verdict in verdicts if verdict.startswith("YES"))
    # Divided by the number of *items*, not the number of lines returned. A judge
    # that answered for only three of five has not thereby made the other two
    # pass, and dividing by its own output length would let a truncated response
    # inflate the score.
    return yes / len(items), f"{yes}/{len(items)}"


def _claims(text: str) -> list[str]:
    """Split an answer or ground truth into checkable statements.

    Sentence-splitting, not a model call. Crude, and deliberately so: a
    model-decomposed claim list is another nondeterministic step between the
    system and its score, and the metric is already judged by a model once.
    """
    parts = [part.strip() for part in text.replace("\n", " ").split(". ")]
    return [part.rstrip(".") for part in parts if len(part.split()) >= 3]


async def score_case(case: RetrievalCase, contexts: list[str], generated: str) -> dict[str, float]:
    """The three metrics for one case."""
    precision, _ = await _judge_fraction(
        f"A user asked: {case.question!r}\n\n"
        "For each passage below, answer YES if it contains information that helps "
        "answer that question, and NO if it is off-topic.",
        contexts,
    )

    joined = "\n\n".join(contexts) or "(no passages were retrieved)"
    recall, _ = await _judge_fraction(
        "Here are the passages that were retrieved:\n\n"
        f"{joined}\n\n"
        "For each statement below, answer YES if the passages above support it, "
        "and NO if they do not.",
        _claims(case.ground_truth),
    )

    faithfulness, _ = await _judge_fraction(
        "Here are the passages an assistant was given:\n\n"
        f"{joined}\n\n"
        "For each statement from its answer below, answer YES if the passages "
        "support it, and NO if the assistant added it from elsewhere.",
        _claims(generated),
    )

    return {
        "context_precision": precision,
        "context_recall": recall,
        "faithfulness": faithfulness,
    }
