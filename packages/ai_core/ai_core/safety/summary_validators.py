"""Guardrails AI validators for generated summaries (docs/SPEC.md §8, layer 4).

Layer 5 (Pydantic) already rejects the wrong *shape*: missing fields, blank
entries, runaway lists, unknown keys. This module is layer 4, and the difference
is the point — these validators need the **source conversation** to decide
anything. "Does this summary preserve the uncertainty the conversation had" is
not a property of the summary alone, and no schema can express it.

The validators are **custom, not Guardrails Hub**. Hub validators are downloaded
at runtime and need `guardrails configure` plus network access and an account;
that is a poor bargain for checks this specific to LearnTrail, and it would make
a summary depend on a third-party service being reachable.

**They are heuristics, and they are deliberately conservative.** A validator here
can be wrong in two directions: passing a bad summary, or blocking a good one.
Blocking a good one is the more damaging failure — the user loses work they
watched being generated — so each check below is written to fire only on clear
evidence, and the semantic version of this job belongs to the Phase 6 evaluation
suite and the Phase 4 `safety-judge` alias, not to string matching.
"""

from __future__ import annotations

import re
from typing import Any, Final

from guardrails.validator_base import (
    FailResult,
    PassResult,
    ValidationResult,
    Validator,
    register_validator,
)

#: Metadata key carrying the conversation a summary was made from. Both
#: validators need it; neither can do anything useful without it.
TRANSCRIPT_KEY: Final = "transcript"

#: Words that mark a conversation as unsettled. Matched case-insensitively on
#: word boundaries, so "may" does not fire on "maybe" being absent nor on
#: "dismay". Chosen to be the vocabulary of genuine hedging rather than of
#: politeness — "please" and "perhaps you could" say nothing about certainty.
_HEDGE_WORDS: Final = frozenset(
    {
        "uncertain",
        "unsure",
        "unclear",
        "maybe",
        "perhaps",
        "possibly",
        "probably",
        "roughly",
        "approximately",
        "depends",
        "varies",
        "sometimes",
        "usually",
        "typically",
        "generally",
        "arguably",
        "disputed",
        "debated",
        "seems",
        "appears",
        "assume",
        "assuming",
        "believe",
        "think",
        "not certain",
        "not sure",
        "i'm not",
        "hard to say",
    }
)

#: How many distinct hedge markers the source must contain before a summary is
#: expected to carry uncertainty forward. One stray "usually" in a long
#: conversation is not a conversation being tentative; two or more is a pattern.
_HEDGE_THRESHOLD: Final = 2


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def _hedge_markers(text: str) -> set[str]:
    lowered = text.lower()
    return {phrase for phrase in _HEDGE_WORDS if _matches(phrase, lowered)}


def _matches(phrase: str, lowered: str) -> bool:
    # Multi-word markers ("not certain") cannot use \b on the whole phrase
    # reliably, so they are checked as substrings; single words get word
    # boundaries so "think" does not fire inside "rethinking".
    if " " in phrase or "'" in phrase:
        return phrase in lowered
    return re.search(rf"\b{re.escape(phrase)}\b", lowered) is not None


@register_validator(name="learntrail/preserves-uncertainty", data_type="string")
class PreservesUncertainty(Validator):
    """A tentative conversation must produce a summary that says so.

    docs/SPEC.md §8 lists "summary must preserve uncertainty" as a layer 4
    validator, and it is the one that matters most here: an approved Learning is
    durable knowledge, so a summary that quietly upgrades "I'm not certain this
    holds everywhere" into a flat assertion is worse than no summary. The user
    would be approving a confidence nobody earned.

    Fires only when the source hedged at least `_HEDGE_THRESHOLD` distinct ways
    and the summary carries none of it forward.
    """

    def validate(self, value: Any, metadata: dict[str, Any]) -> ValidationResult:
        transcript = metadata.get(TRANSCRIPT_KEY)
        if not transcript:
            # No source to compare against. Passing is right: this validator has
            # nothing to say, and failing would block every summary whose caller
            # forgot the metadata — turning a wiring mistake into a data outage.
            return PassResult()

        source_hedges = _hedge_markers(str(transcript))
        if len(source_hedges) < _HEDGE_THRESHOLD:
            return PassResult()

        if _hedge_markers(str(value)):
            return PassResult()

        return FailResult(
            error_message=(
                "the conversation was tentative "
                f"({', '.join(sorted(source_hedges)[:4])}) but the summary states "
                "everything as settled; uncertainty must be preserved"
            ),
        )


@register_validator(name="learntrail/grounded-in-transcript", data_type="string")
class GroundedInTranscript(Validator):
    """The summary must not introduce topics the conversation never mentioned.

    docs/SPEC.md §8 lists "summary must not introduce unsupported topics". This
    is a *coverage* check, not a fact check: it measures how much of the
    summary's distinctive vocabulary appears in the source at all. A summary
    inventing a tool, library, or concept that was never discussed shows up as
    unfamiliar words; one that paraphrases faithfully does not.

    **This check does not run on short conversations, and that limit was learned
    the hard way.** An earlier version applied the ratio unconditionally and
    rejected a correct summary of a two-turn exchange, calling "allows",
    "behavior", "database" and "difference" invented topics. They were ordinary
    paraphrase. A short transcript simply has too small a vocabulary for overlap
    to mean anything: the summary is *supposed* to use words the speakers did
    not.

    So the check is gated twice — a minimum source size, and a lenient threshold
    — and it therefore catches only gross invention on a substantial
    conversation. That is the honest limit of string matching. The real version
    of "did this summary make something up" is a judge model (the `safety-judge`
    alias) and the Phase 6 evaluation suite; this is a cheap guard that runs on
    every draft, not a replacement for either.
    """

    #: Distinct content words a transcript must have before the ratio is
    #: meaningful. Below this, normal paraphrase looks like invention.
    MIN_SOURCE_WORDS: Final = 120

    #: Fraction of a summary's distinctive words that must appear in the source.
    #: Low, because paraphrase is the job: the check exists to catch a summary
    #: that is *mostly* about something else, not one that chose better words.
    OVERLAP_THRESHOLD: Final = 0.25

    #: Words too common to carry topical meaning. Their presence or absence says
    #: nothing about whether a topic was invented.
    STOPWORDS: Final = frozenset(
        [
            "a",
            "an",
            "the",
            "and",
            "or",
            "but",
            "if",
            "then",
            "than",
            "that",
            "this",
            "these",
            "those",
            "of",
            "in",
            "on",
            "at",
            "to",
            "for",
            "from",
            "with",
            "without",
            "by",
            "as",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "it",
            "its",
            "it's",
            "you",
            "your",
            "we",
            "our",
            "they",
            "their",
            "he",
            "she",
            "not",
            "no",
            "nor",
            "so",
            "such",
            "can",
            "could",
            "may",
            "might",
            "must",
            "shall",
            "should",
            "will",
            "would",
            "do",
            "does",
            "did",
            "done",
            "have",
            "has",
            "had",
            "having",
            "what",
            "which",
            "who",
            "whom",
            "when",
            "where",
            "why",
            "how",
            "all",
            "any",
            "both",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "only",
            "own",
            "same",
            "too",
            "very",
            "just",
            "about",
            "into",
            "over",
            "under",
            "again",
            "further",
            "once",
            "here",
            "there",
        ]
    )

    def validate(self, value: Any, metadata: dict[str, Any]) -> ValidationResult:
        transcript = metadata.get(TRANSCRIPT_KEY)
        if not transcript:
            return PassResult()

        source_words = _words(str(transcript))
        if len(source_words - self.STOPWORDS) < self.MIN_SOURCE_WORDS:
            # Too small a source for the ratio to distinguish paraphrase from
            # invention. Passing is correct: a check that cannot tell the
            # difference must not be the thing that discards a user's summary.
            return PassResult()

        summary_words = _words(str(value)) - self.STOPWORDS
        # Drop very short tokens: "id", "db", "x" carry no topical signal and
        # skew a ratio computed over a small vocabulary.
        summary_words = {word for word in summary_words if len(word) > 3}
        if not summary_words:
            return PassResult()
        grounded = summary_words & source_words
        overlap = len(grounded) / len(summary_words)

        if overlap >= self.OVERLAP_THRESHOLD:
            return PassResult()

        invented = sorted(summary_words - source_words)[:6]
        return FailResult(
            error_message=(
                f"only {overlap:.0%} of the summary's vocabulary appears in the "
                f"conversation (needs {self.OVERLAP_THRESHOLD:.0%}); it may describe "
                f"topics that were never discussed, e.g. {', '.join(invented)}"
            ),
        )
