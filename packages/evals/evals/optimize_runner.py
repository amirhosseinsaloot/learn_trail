"""Running the optimization (docs/SPEC.md §9, Phase 9).

Separate from `optimize`, which holds the dataset, the split and the comparison
and needs neither DSPy nor a gateway. This is the part that calls models, and the
split keeps `optimize` unit-testable — including the one property the criterion
rests on, that train and held-out are disjoint.

**DSPy is pointed at the LiteLLM gateway by alias** (CLAUDE.md invariant #2). It
would otherwise call OpenAI directly with a key from the environment, which is
exactly the credential path invariant #3 forbids.

**The optimizer never sees the held-out set.** `optimise()` takes `train` and is
given nothing else; `compare()` is what touches `held_out`, after optimization
has finished. That is the whole design — everything else here is plumbing.
"""

from __future__ import annotations

import asyncio
from typing import Any, Final

from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import gateway_key, gateway_url
from evals.optimize import Comparison, OptimizationCase, split

#: The alias whose prompt is being optimized. `learning_summary` runs on
#: `learning-deep` (prompts/learning_summary/v1.toml), and optimizing against a
#: different model than the one that will serve it would measure the wrong thing.
TASK_ALIAS: Final = ModelAlias.LEARNING_DEEP

#: Temperature for everything here, for the same reason the evaluation suite pins
#: it: a comparison needs the system under test to hold still.
TEMPERATURE: Final = 0.0

#: How many times each score is measured before comparing.
#:
#: **Added after two consecutive runs returned opposite verdicts** — IMPROVED
#: (+0.08 held-out) and then OVERFITTED (train +0.10, held-out -0.08). Even at
#: temperature 0 the provider is not bit-reproducible without a seed, and with
#: four held-out cases a single case shifting by half a point moves the verdict.
#:
#: Averaging does not create statistical power that nine cases do not have. What
#: it does is stop the *measurement* being the loudest source of variance, so
#: what remains is the dataset's own limits — which are stated rather than
#: papered over.
REPEATS: Final = 3

#: COPRO's search size. Small on purpose — every candidate instruction is
#: generated and then scored against all five training cases, so cost grows as
#: breadth x depth x |train|. Enough to explore, bounded enough that a run is
#: minutes and cents rather than hours.
BREADTH: Final = 3
DEPTH: Final = 2


def _configure_dspy() -> None:
    """Point DSPy at the gateway, by alias."""
    import dspy

    dspy.configure(
        lm=dspy.LM(
            # `openai/<alias>` is LiteLLM's routing form, and the alias is the
            # gateway's vocabulary — no provider model is named here.
            f"openai/{TASK_ALIAS.value}",
            api_base=f"{gateway_url()}/v1",
            api_key=gateway_key(),
            temperature=TEMPERATURE,
            max_tokens=4000,
            cache=False,
        )
    )


def _signature() -> Any:
    """The task, as a DSPy signature.

    Deliberately mirrors what `learning_summary` actually does — transcript in,
    structured summary out — because the instruction COPRO produces is going to
    be proposed as a version of *that* prompt. A signature describing a different
    task would optimize an instruction nothing could use.
    """
    import dspy

    class Summarise(dspy.Signature):
        """Distil a learning conversation into a structured summary."""

        transcript: str = dspy.InputField(desc="the conversation to summarise")
        overview: str = dspy.OutputField(desc="one paragraph worth re-reading in six months")
        key_concepts: str = dspy.OutputField(
            desc="the ideas the conversation established, one per line"
        )
        uncertainty: str = dspy.OutputField(
            desc="anything the conversation left unsettled; empty if it settled everything"
        )

    return Summarise


def _metric(case: Any, prediction: Any, trace: object = None) -> float:
    """Score one summary in [0, 1]. Deterministic — no judge model.

    Two halves, and the forbidden half is absolute:

        coverage   fraction of `required_points` whose keywords appear
        clean      0 if any forbidden claim appears, else 1

    A judged metric would be more discerning and would also put a
    nondeterministic model inside the optimizer's own scoring loop, where its
    noise compounds across every candidate. This one is crude and stable, and
    stability is what a comparison needs. The judged metrics live in the golden
    suite, which is where the promoted prompt has to pass anyway.
    """
    text = " ".join(
        str(getattr(prediction, field, "")) for field in ("overview", "key_concepts", "uncertainty")
    ).lower()

    forbidden = [claim for claim in case.forbidden_claims if claim.lower() in text]
    if forbidden:
        return 0.0

    if not case.required_points:
        return 1.0

    covered = 0
    for point in case.required_points:
        # Keyword overlap, not substring: a summary rephrases, so requiring the
        # literal sentence would score every good summary at zero. Words of four
        # letters or more, because "a", "of" and "the" match everything.
        words = [word for word in point.lower().split() if len(word) >= 4]
        if words and sum(word in text for word in words) / len(words) >= 0.6:
            covered += 1
    return covered / len(case.required_points)


def _as_examples(cases: tuple[OptimizationCase, ...]) -> list[Any]:
    import dspy

    return [
        dspy.Example(
            transcript=case.transcript,
            required_points=case.required_points,
            forbidden_claims=case.forbidden_claims,
        ).with_inputs("transcript")
        for case in cases
    ]


def _score(program: Any, cases: tuple[OptimizationCase, ...]) -> float:
    """Mean metric over a set, averaged over `REPEATS` passes.

    Sequential — the sets are single digits, and a thread pool would add a
    concurrency variable to a measurement whose whole purpose is to hold
    variables still.
    """
    examples = _as_examples(cases)
    if not examples:
        return 0.0
    total = 0.0
    for _ in range(REPEATS):
        total += sum(
            _metric(example, program(transcript=example.transcript)) for example in examples
        ) / len(examples)
    return total / REPEATS


def run_optimization() -> Comparison:
    """Optimize on train, then compare baseline and candidate on held-out."""
    import dspy
    from dspy.teleprompt import COPRO

    _configure_dspy()
    train, held_out = split()

    baseline = dspy.Predict(_signature())

    # The only place the optimizer is given data, and it is `train`. `held_out` is
    # not in scope in this block — which is the criterion, expressed as code
    # rather than as a promise.
    optimizer = COPRO(metric=_metric, breadth=BREADTH, depth=DEPTH, init_temperature=1.0)
    candidate = optimizer.compile(
        baseline,
        trainset=_as_examples(train),
        eval_kwargs={"num_threads": 1, "display_progress": False},
    )

    instruction = ""
    for predictor in candidate.predictors():
        instruction = str(getattr(predictor.signature, "instructions", ""))
        break

    return Comparison(
        baseline_train=_score(baseline, train),
        baseline_held_out=_score(baseline, held_out),
        candidate_train=_score(candidate, train),
        candidate_held_out=_score(candidate, held_out),
        instruction=instruction,
    )


async def run_optimization_async() -> Comparison:
    """DSPy is synchronous; keep it off the event loop the CLI runs on."""
    return await asyncio.to_thread(run_optimization)
