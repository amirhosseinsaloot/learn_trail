"""The model aliases, as a type.

CLAUDE.md invariant #2 says application code requests an alias and never a
provider/model string. A bare `str` would let that rule be broken by a typo;
making the alias an enum means `complete(alias="gpt-4o")` does not type-check
and `ModelAlias("gpt-4o")` raises at runtime. The invariant stops being a
convention someone has to remember and becomes something the type checker
enforces.

The values here must match the `model_name` entries in
infra/litellm/config.yaml exactly — that file maps them onto real models, and it
is the only place a provider is named.
"""

from enum import StrEnum


class ModelAlias(StrEnum):
    """A model role, not a model.

    Which model actually serves each of these is a deployment decision that lives
    in infra/litellm/config.yaml. Application code chooses the *role*: is this
    answer on the hot path, does it need the strong model, or is it a judgement
    about someone else's output?
    """

    #: The hot path: chat answers. Every question in every conversation.
    LEARNING_FAST = "learning-fast"

    #: Work that must be right rather than quick — structured summaries, and
    #: anything an approved Learning is derived from (docs/SPEC.md §15, Phase 3).
    LEARNING_DEEP = "learning-deep"

    #: LLM-as-judge for the safety pipeline (Phase 4) and evaluations (Phase 6).
    #: Runs on every request in those phases, so its cost multiplies by traffic.
    SAFETY_JUDGE = "safety-judge"
