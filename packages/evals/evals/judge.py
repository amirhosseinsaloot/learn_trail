"""The judge model, and the metrics built on it (docs/SPEC.md §9, Phase 6).

**The judge goes through the gateway like everything else.** DeepEval will
happily talk to OpenAI directly if handed a key, which would put a provider
credential in this process and break CLAUDE.md invariant #3. Instead it is given
a custom model that wraps `ai_core`'s gateway client, so the judge is the
`safety-judge` alias and the credential stays where it belongs.

**A judge is a model, so it is wrong sometimes.** docs/SPEC.md §9 says as much —
"AI judges are not sufficient" — which is why every metric here produces a
`reason` and why `evaluation_result.explanation` is not optional. A score with no
argument attached cannot be reviewed, and an unreviewable score is one you either
trust blindly or ignore.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import client

if TYPE_CHECKING:  # pragma: no cover - import-time only for type checkers
    from deepeval.models import DeepEvalBaseLLM

#: Bumped when a metric's prompt or threshold changes. Recorded on every
#: `evaluation_result`, because a threshold that moved makes today's 0.8
#: incomparable with last month's — and without the version the history would
#: look like a regression that never happened.
METRIC_VERSION: Final = "learntrail_metrics@1"

#: The alias that judges.
#:
#: **This was `safety-judge` and had to change.** The cheap tier looked like the
#: obvious choice — judging is a classification task run many times per suite, so
#: the expensive alias makes an evaluation cost more than the answers it grades.
#: That reasoning is sound for the *safety* rails, where the question is a coarse
#: yes/no. It was wrong here, and wrong in the most damaging way.
#:
#: With `safety-judge`, two cases failed repeatedly. Both answers were correct.
#: Asked "In one sentence only: what is a foreign key?", the system answered:
#:
#:     "A foreign key is a column or a set of columns in a database table that
#:      establishes a link between data in two tables by referencing the primary
#:      key of another table."
#:
#: That is one sentence and it does reference another table's key — both grading
#: notes, exactly satisfied. The judge scored it 0.40-0.60 and explained that it
#: "fails to encapsulate the definition in a single sentence". The other case was
#: the same shape: an answer that opens "You're correct that PostgreSQL is
#: primarily a relational database" was marked down for failing to accept the
#: correction.
#:
#: GEval scores by token probability over a rubric, which asks more of a model
#: than a yes/no rail does. On `learning-deep` both cases pass on consecutive
#: runs. The cost difference is real; a suite that fails correct answers is worse
#: than no suite, because it teaches you to ignore the one that eventually
#: catches something.
#:
#: Worth recording how close this came to being misread: the judge's explanations
#: were fluent and specific, and reading them alone led to a diagnosis of a
#: missing chat system prompt. Only looking at the actual answers showed the
#: system was right and the judge was not.
JUDGE_ALIAS: Final = ModelAlias.LEARNING_DEEP


def gateway_judge() -> DeepEvalBaseLLM:
    """A DeepEval model backed by the LiteLLM gateway.

    Imported lazily inside the function: DeepEval is an optional extra, and this
    module is imported by the runner, which must be importable in a checkout
    that never installed it.
    """
    from deepeval.models import DeepEvalBaseLLM

    class GatewayJudge(DeepEvalBaseLLM):
        def get_model_name(self) -> str:
            return JUDGE_ALIAS.value

        def load_model(self) -> Any:
            return client()

        def generate(self, prompt: str, *args: Any, **kwargs: Any) -> str:
            # DeepEval's sync path. Everything in this repo is async, so the sync
            # entry point exists only because the library requires it; the async
            # one below is what actually runs.
            raise NotImplementedError("use the async metrics; this repo has no sync gateway path")

        async def a_generate(self, prompt: str, *args: Any, **kwargs: Any) -> str:
            completion = await client().chat.completions.create(
                model=JUDGE_ALIAS.value,
                messages=[{"role": "user", "content": prompt}],
            )
            return completion.choices[0].message.content or ""

    return GatewayJudge()
