"""The evaluation suite, as pytest tests (docs/SPEC.md §9, "DeepEval").

**Every test here is `slow`, which is a contract, not a hint.** `make test` runs
`-m "not slow and not phase"`, so none of this executes in the FAST lane, in a
git hook, or in `make status`. These call real models and cost real money;
docs/CODE_QUALITY.md's lane design exists precisely so that a paid,
nondeterministic check can never end up on the path a developer walks fifty times
a day.

Run them with `make evals`, which also records the gate manifest — running this
file with bare pytest scores the system but does not clear the merge gate, and
that asymmetry is deliberate: the gate records *full* runs only.

The test names come from docs/SPEC.md §9's own list.
"""

from __future__ import annotations

import importlib.util

import pytest
from evals.datasets import EvaluationCase, load_suite
from evals.runner import check_forbidden_claims, check_safety_policy

pytestmark = [pytest.mark.slow, pytest.mark.anyio]

#: DeepEval is the optional `judges` extra. Skipping rather than erroring when it
#: is absent keeps `pytest -m slow` meaningful in a checkout that installed only
#: the runtime — an ImportError would surface as a quality failure, which is the
#: same category error the `rails_unavailable` guard exists to prevent.
needs_judge = pytest.mark.skipif(
    importlib.util.find_spec("deepeval") is None,
    reason="the `judges` extra is not installed — run `make evals`",
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _answer(case: EvaluationCase) -> str:
    from ai_core.models.aliases import ModelAlias
    from ai_core.models.gateway import complete
    from ai_core.schemas.completion import ChatTurn, CompletionRequest

    response = await complete(
        CompletionRequest(
            alias=ModelAlias.LEARNING_FAST,
            messages=[ChatTurn(role=turn.role, content=turn.content) for turn in case.messages],
        )
    )
    return response.text


@pytest.mark.parametrize("case", load_suite("conversations"), ids=lambda case: case.id)
async def test_answer_does_not_make_a_forbidden_claim(case: EvaluationCase) -> None:
    """The regression half of the conversation suite.

    `forbidden_claims` holds phrases a previous failure actually produced —
    including the planted wrong answer in the correction case — so this is where
    a fixed bug stops being able to come back.
    """
    result = check_forbidden_claims(case, await _answer(case))
    assert result.passed, result.explanation


@needs_judge
@pytest.mark.parametrize("case", load_suite("conversations"), ids=lambda case: case.id)
async def test_answer_relevance(case: EvaluationCase) -> None:
    """Does the answer address the question that was actually asked?

    The judged half, and the one that needs a model: relevance to a multi-turn
    conversation is not a substring check. Scored against `THRESHOLDS`, which is
    deliberately below 1.0 — a judge is itself nondeterministic, and a perfect
    bar would fail on noise, teaching everyone to rerun until green.
    """
    from evals.runner import _judge

    results = await _judge("conversations", case, await _answer(case))
    for result in results:
        assert result.passed, f"{result.score}: {result.explanation}"


@pytest.mark.parametrize("case", load_suite("summaries"), ids=lambda case: case.id)
async def test_summary_is_faithful_to_the_chat(case: EvaluationCase) -> None:
    """A summary may only contain what the conversation contained.

    The failure this guards is not a wrong summary but a *plausible* one: an
    invented-but-true fact passes a reader's eye and then becomes a Learning,
    which is the point at which the product starts lying to its user.
    """
    from ai_core.agents.summariser import summarise

    transcript = "\n".join(f"{turn.role}: {turn.content}" for turn in case.messages)
    generated = await summarise(transcript)
    rendered = generated.summary.model_dump_json()

    result = check_forbidden_claims(case, rendered)
    assert result.passed, result.explanation


@pytest.mark.parametrize("case", load_suite("summaries"), ids=lambda case: case.id)
async def test_summary_preserves_uncertainty(case: EvaluationCase) -> None:
    """A conversation that ended unsettled must not be summarised as settled.

    Only asserted for the cases tagged for it. Confidence the model did not earn
    is what makes an approved Learning dangerous, because approval is what makes
    it trusted.
    """
    if "uncertainty" not in case.tags:
        pytest.skip("not an uncertainty case")

    from ai_core.agents.summariser import summarise

    transcript = "\n".join(f"{turn.role}: {turn.content}" for turn in case.messages)
    summary = (await summarise(transcript)).summary
    hedged = summary.open_questions or summary.uncertainty_notes
    assert hedged, "the conversation ended unsettled but the summary recorded no uncertainty"


@pytest.mark.parametrize("case", load_suite("safety"), ids=lambda case: case.id)
async def test_safety_policy_compliance(case: EvaluationCase) -> None:
    """The pipeline must decide what the case says it should.

    Both directions. Half these cases are attacks that must be blocked and half
    are benign inputs that must not be — a suite of only the first would be
    passed perfectly by a system that refuses everything.
    """
    result = await check_safety_policy(case)
    assert result.passed, result.explanation
