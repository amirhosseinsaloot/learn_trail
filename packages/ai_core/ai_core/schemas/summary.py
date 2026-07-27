"""The structured summary schema (docs/SPEC.md §7).

This is the shape a conversation is distilled into, and — once a human approves
it — the shape of a Learning. CLAUDE.md invariant #4 says every structured model
output is parsed through a Pydantic schema before it touches persistence; for
Phase 3 this *is* that schema, and the Phase 3 exit criterion is that malformed
or incomplete summaries are rejected before persistence.

**Where the limits come from.** Every constraint below is a rejection rule, and
each exists because the model can plausibly produce the thing it forbids. They
are structural (docs/SPEC.md §8 layer 5) — "does this have the right shape" —
and deliberately not semantic. Whether a summary is *faithful* to the
conversation is layer 4's job (`ai_core.safety` validators) and, later, Phase 6's
evaluation suite. A schema cannot tell you a well-formed summary is wrong.

**Empty lists are legal; missing fields are not.** A conversation that settled
everything has no open questions, and forcing the model to invent one would be
worse than an empty list. But a *missing* `open_questions` means the model did
not answer the question at all, which is exactly the "incomplete" the exit
criterion names.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

#: Trimmed, non-empty. A list entry of "   " is the model padding to length; it
#: renders as a blank bullet and means nothing.
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]

#: Upper bounds are guards against a model that will not stop, not editorial
#: preferences. A 200-item `key_concepts` is a failure mode, not a thorough
#: summary, and it would arrive as a wall of text in the review UI.
MAX_ITEMS = 20


class LearningSummary(BaseModel):
    """A model-generated draft of what a conversation taught.

    Never knowledge on its own. It becomes a Learning only when a human approves
    it (CLAUDE.md invariant #5), which is why this type has no `approved` field:
    approval is an event recorded on a different table, not a flag a model output
    could ever carry.
    """

    # `extra="forbid"` is load-bearing for the exit criterion. Without it, a
    # model returning `{"titel": ..., "title": ...}` — or inventing a field
    # nothing reads — would validate, and the typo'd content would be silently
    # dropped rather than rejected. "Unknown fields appear where strict parsing
    # is required" is listed in docs/SPEC.md §8 layer 5 as a reject condition.
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Short enough to be a list item in My Learnings. The model will happily
    #: write a sentence here if not bounded.
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

    #: The one paragraph worth re-reading in six months. Bounded below because a
    #: three-word overview is not a summary, and above because an overview that
    #: runs to a page is the model reproducing the transcript.
    overview: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=40, max_length=2000)
    ]

    #: What the conversation established. Required to be non-empty: a
    #: conversation worth keeping taught at least one thing, and a summary with
    #: no concepts is the model failing rather than the conversation being empty.
    key_concepts: list[Line] = Field(min_length=1, max_length=MAX_ITEMS)

    #: Things the conversation actively contrasted ("X versus Y"). May be empty —
    #: plenty of conversations never contrast anything.
    distinctions: list[Line] = Field(default_factory=list, max_length=MAX_ITEMS)

    examples: list[Line] = Field(default_factory=list, max_length=MAX_ITEMS)

    #: What was left unresolved. May be empty, but see `uncertainty_notes`: a
    #: summary claiming both no open questions and no uncertainty about a long
    #: exploratory conversation is usually the model smoothing over the parts it
    #: did not follow.
    open_questions: list[Line] = Field(default_factory=list, max_length=MAX_ITEMS)

    suggested_tags: list[Line] = Field(default_factory=list, max_length=MAX_ITEMS)

    #: Where the conversation was tentative or the model is unsure. docs/SPEC.md
    #: §8 layer 4 lists "summary must preserve uncertainty" as a validator, and
    #: this is the field it validates — confidence the conversation did not earn
    #: is the failure mode that makes an approved Learning dangerous.
    uncertainty_notes: list[Line] = Field(default_factory=list, max_length=MAX_ITEMS)

    @property
    def is_hedged(self) -> bool:
        """Whether the summary admits to any uncertainty at all."""
        return bool(self.open_questions or self.uncertainty_notes)
