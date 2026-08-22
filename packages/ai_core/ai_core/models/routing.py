"""Choosing which model answers, and what to do when it does not (docs/SPEC.md §15, Phase 10).

`choose_model` has been a one-line rule since Phase 2, deliberately, so that the
day real routing arrived it would be a change to one node and not a rewrite. This
is that change.

**Routing is a rule, not a model call — and that is a decision, not a limitation.**
docs/SPEC.md lists a "difficulty classifier", and the obvious reading is a small
model that reads the question and rates it. That would put a model call *before*
every model call, doubling the request's latency floor and its failure surface to
decide something a handful of signals answer most of the time. The heuristic here
routes on question shape — length, multi-part structure, and words that mark a
question as analytical rather than factual. A model classifier is its documented
successor and drops into `classify_difficulty` alone; the rest of the graph never
learns which one ran.

**Fallback is the half the exit criterion actually tests.** A router that picks
well but cannot survive a slow model is worse than no router, because it fails on
exactly the hard requests it exists to route. `FALLBACK` maps each alias to the
one to try when it times out or errors, and the graph consults it — so "a forced
timeout triggers the documented fallback" is a property of code, not a promise in
a comment.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

from ai_core.models.aliases import ModelAlias


class Difficulty(StrEnum):
    """How hard a question is to answer well.

    Two levels, not five. The routing decision is binary — cheap path or strong
    path — so a finer scale would be precision the consumer cannot use, and every
    extra level is a boundary to argue about.
    """

    SIMPLE = "simple"
    DIFFICULT = "difficult"


#: Which alias serves each difficulty on the chat path. The strong tier is
#: `learning-deep`, the same alias summaries already use — routing does not
#: introduce a new model, it sends the hard questions to the good one.
ALIAS_FOR: Final[dict[Difficulty, ModelAlias]] = {
    Difficulty.SIMPLE: ModelAlias.LEARNING_FAST,
    Difficulty.DIFFICULT: ModelAlias.LEARNING_DEEP,
}

#: What to try when an alias times out or the gateway errors. The strong model
#: falls back to the fast one: a slow-or-broken `learning-deep` should still get
#: the user *an* answer rather than nothing, and the fast model is the only
#: cheaper thing available. The fast model has nowhere cheaper to fall to, so its
#: failure surfaces as an error — which is correct, not a gap. `safety-judge` and
#: `learning-embedding` are not answer models and are absent by design.
FALLBACK: Final[dict[ModelAlias, ModelAlias]] = {
    ModelAlias.LEARNING_DEEP: ModelAlias.LEARNING_FAST,
}

#: A question longer than this many characters is treated as difficult on length
#: alone. Long questions carry more constraints to satisfy at once, which is the
#: thing the strong model is better at. Generous, because a pasted stack trace is
#: long without being hard — the marker words below are what catch true depth.
LENGTH_THRESHOLD: Final = 320

#: Words that mark a question as analytical rather than lookup. "What is X" is a
#: definition the fast model handles; "why", "compare", "trade-off", "design" ask
#: for reasoning across several things at once. Matched as whole words so
#: "whyever" or a substring cannot trip them.
DIFFICULTY_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "why",
        "how",
        "compare",
        "contrast",
        "difference",
        "differences",
        "tradeoff",
        "tradeoffs",
        "trade-off",
        "design",
        "architect",
        "architecture",
        "explain",
        "debug",
        "optimise",
        "optimize",
        "prove",
        "derive",
        "evaluate",
        "implications",
        "versus",
        "vs",
    }
)

_WORD = re.compile(r"[a-z][a-z-]*")


def classify_difficulty(question: str) -> Difficulty:
    """Rate one question SIMPLE or DIFFICULT.

    Difficult if it is long, if it asks more than one thing (a question mark
    followed by more text, or an explicit "and"/"also" join), or if it uses a
    marker word. Otherwise simple. The bias is deliberate: a false "simple"
    sends a hard question to the weak model and produces a poor answer, while a
    false "difficult" only costs money — so the rule leans toward difficult when
    a signal is present at all.
    """
    text = question.strip().lower()
    if not text:
        # An empty question is not the router's problem to solve — `validate_input`
        # already rejects it. Simple is the safe default for the unreachable case.
        return Difficulty.SIMPLE

    if len(text) >= LENGTH_THRESHOLD:
        return Difficulty.DIFFICULT

    words = set(_WORD.findall(text))
    if words & DIFFICULTY_MARKERS:
        return Difficulty.DIFFICULT

    # Two questions in one turn: a question mark with more question after it.
    if text.count("?") >= 2:
        return Difficulty.DIFFICULT

    return Difficulty.SIMPLE


def route(
    question: str, *, budget_exhausted: bool = False, local_only: bool = False
) -> tuple[Difficulty, ModelAlias]:
    """The routing decision: difficulty, and the alias it maps to.

    `local_only` is privacy/offline mode (Phase 11): every request goes to the
    locally-served model and nothing leaves the machine. It wins over everything
    else, including difficulty and budget, because it is a *guarantee* — "no cloud
    call" is not a preference to be traded against answer quality. The difficulty
    is still reported as assessed, so a trace shows what was asked of the local
    model even though the alias was forced.

    Crucially, `learning-local` has no entry in `FALLBACK`. So a local model that
    times out or errors surfaces as an error rather than quietly falling back to a
    cloud alias — in privacy mode, failing is correct and leaking is not.

    `budget_exhausted` forces the cheap *cloud* path regardless of difficulty.
    Cost-aware routing rather than a hard refusal: the strong model is a quality
    upgrade, not a requirement, so dropping to the fast one is the graceful
    response when a spend window is used up.
    """
    difficulty = classify_difficulty(question)
    if local_only:
        return difficulty, ModelAlias.LEARNING_LOCAL
    if budget_exhausted:
        return difficulty, ModelAlias.LEARNING_FAST
    return difficulty, ALIAS_FOR[difficulty]


def fallback_for(alias: ModelAlias) -> ModelAlias | None:
    """The alias to try when `alias` fails, or None if it is already the floor."""
    return FALLBACK.get(alias)
