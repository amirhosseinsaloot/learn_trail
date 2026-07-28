"""What a safety check decided, and why (docs/SPEC.md §8).

The vocabulary the whole pipeline speaks. Every check — NeMo rail, PII scan,
Guardrails validator — returns one of these, so the graph, the database and the
UI all reason about the same six actions rather than each inventing a boolean.

**A decision is a record, not a side effect.** docs/SPEC.md §8 stores safety
decisions separately from the content they judged, which is what makes an audit
possible: the message says what was said, the `safety_event` says what the system
thought about it, and neither is rewritten to reflect the other.

The exit criterion for Phase 4 is "every model interaction has an explicit,
testable safety path". `SafetyDecision` is the "explicit" half — a check that
merely returned `True` would leave the reason, the stage and the severity
unrecorded, and there would be nothing to test but a boolean.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SafetyStage(StrEnum):
    """Where in the request a decision was made (docs/SPEC.md §8's `stage`).

    Recorded because the same policy can reach different conclusions at
    different points — a phrase that is fine in a question can be a problem in an
    answer — and an audit that cannot tell input from output cannot explain
    either.
    """

    INPUT = "input"
    OUTPUT = "output"


class SafetyAction(StrEnum):
    """What the system did about it — docs/SPEC.md §8's action list, verbatim.

    Ordered from most permissive to most restrictive, which is what
    `SafetyOutcome.action` relies on when several checks disagree: the strictest
    one wins, because a check that says "block" has seen something the others
    did not.
    """

    ALLOW = "allow"
    ALLOW_WITH_WARNING = "allow_with_warning"
    REDACT = "redact"
    RETRY = "retry"
    BLOCK = "block"
    REQUIRE_REVIEW = "require_review"


#: Restrictiveness order. Used to combine decisions; not stored anywhere.
_SEVERITY_ORDER: dict[SafetyAction, int] = {
    SafetyAction.ALLOW: 0,
    SafetyAction.ALLOW_WITH_WARNING: 1,
    SafetyAction.REDACT: 2,
    SafetyAction.RETRY: 3,
    SafetyAction.REQUIRE_REVIEW: 4,
    SafetyAction.BLOCK: 5,
}


class SafetyDecision(BaseModel):
    """One check's verdict.

    Mirrors the `safety_event` columns of docs/SPEC.md §8 so that persisting one
    is a field-for-field copy rather than a translation — a translation is where
    an audit trail quietly loses the thing it was built to keep.
    """

    model_config = ConfigDict(frozen=True)

    stage: SafetyStage
    #: Which check produced this, e.g. `nemo_input_rail`, `pii_scan`.
    policy_name: str = Field(min_length=1)
    #: The version of that policy. A recorded decision that cannot say *which*
    #: version of a rule judged it is not auditable — the rule changes, and the
    #: history becomes a claim about text nobody can reconstruct.
    policy_version: str = Field(min_length=1)
    action: SafetyAction
    #: 0 for allow, rising with restrictiveness. Deliberately derived rather than
    #: chosen per call site, so two checks cannot rate the same action
    #: differently.
    severity: int = Field(ge=0)
    #: What kind of concern, e.g. `jailbreak`, `pii`. Free-form and plural: one
    #: input can trip several.
    categories: list[str] = Field(default_factory=list)
    #: Why, in words a human reviewing the audit can act on.
    explanation: str = ""

    @classmethod
    def allow(cls, stage: SafetyStage, policy_name: str, policy_version: str) -> SafetyDecision:
        """The common case, spelled once.

        Allowed interactions are recorded too, not just refusals. "Every model
        interaction has an explicit safety path" is not satisfied by a system
        that only writes a row when it says no — that would leave the pass case
        indistinguishable from the case where no check ran at all.
        """
        return cls(
            stage=stage,
            policy_name=policy_name,
            policy_version=policy_version,
            action=SafetyAction.ALLOW,
            severity=_SEVERITY_ORDER[SafetyAction.ALLOW],
        )

    @classmethod
    def refuse(
        cls,
        stage: SafetyStage,
        policy_name: str,
        policy_version: str,
        *,
        action: SafetyAction,
        categories: list[str],
        explanation: str,
    ) -> SafetyDecision:
        return cls(
            stage=stage,
            policy_name=policy_name,
            policy_version=policy_version,
            action=action,
            severity=_SEVERITY_ORDER[action],
            categories=categories,
            explanation=explanation,
        )

    @property
    def blocks(self) -> bool:
        """Whether this decision stops the interaction.

        `REQUIRE_REVIEW` blocks too: it means a human must look before this
        proceeds, and continuing while waiting would make the review pointless.
        """
        return self.action in (SafetyAction.BLOCK, SafetyAction.REQUIRE_REVIEW)

    @property
    def warns(self) -> bool:
        """Whether the user should be told, without being stopped."""
        return self.action is SafetyAction.ALLOW_WITH_WARNING


class SafetyOutcome(BaseModel):
    """Every decision made at one stage, and what they add up to.

    All of them are kept, not just the decisive one. An audit that recorded only
    the blocking check would lose the fact that two other policies also had
    concerns — which is exactly the pattern that distinguishes a borderline case
    from a clear one.
    """

    model_config = ConfigDict(frozen=True)

    stage: SafetyStage
    decisions: list[SafetyDecision] = Field(default_factory=list)

    @property
    def action(self) -> SafetyAction:
        """The strictest action any check asked for."""
        if not self.decisions:
            return SafetyAction.ALLOW
        return max(
            (decision.action for decision in self.decisions),
            key=lambda action: _SEVERITY_ORDER[action],
        )

    @property
    def blocks(self) -> bool:
        return any(decision.blocks for decision in self.decisions)

    @property
    def warnings(self) -> list[SafetyDecision]:
        return [decision for decision in self.decisions if decision.warns]

    @property
    def categories(self) -> list[str]:
        """Every concern raised at this stage, deduplicated, in the order found.

        From all decisions that were not a plain allow, including ones that only
        warned: "blocked for injection, and by the way there is an API key in
        here" is two facts, and dropping the second because the first was more
        severe would lose the one the user can still act on.
        """
        seen: list[str] = []
        for decision in self.decisions:
            if decision.action is SafetyAction.ALLOW:
                continue
            seen.extend(c for c in decision.categories if c not in seen)
        return seen

    @property
    def notice(self) -> str:
        """Why the user is being told anything at all.

        Wider than `explanation`: every check that was not a plain allow, warnings
        included. A blocked outcome has an `explanation`; a *warned* one does not,
        and reporting only the blocking reasons would leave a warning banner with
        nothing to say — which is how "your message contains an API key" becomes
        the useless "a safety check flagged this turn".
        """
        reasons = [
            decision.explanation
            for decision in self.decisions
            if decision.action is not SafetyAction.ALLOW and decision.explanation
        ]
        return "; ".join(reasons)

    @property
    def explanation(self) -> str:
        """Why the interaction was stopped, if it was.

        Only the blocking reasons: a user told "your message was blocked" also
        needs to know which concern did it, and listing the checks that passed
        would bury that.
        """
        return "; ".join(d.explanation for d in self.decisions if d.blocks and d.explanation)
