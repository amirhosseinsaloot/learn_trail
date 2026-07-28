"""The safety pipeline (docs/SPEC.md §8).

Two entry points — `check_input` and `check_output` — each returning a
`SafetyOutcome` describing every check that ran. The Phase 4 exit criterion is
"every model interaction has an explicit, testable safety path", and this module
is where "explicit" is decided: both functions always return an outcome, and an
allowed interaction produces `ALLOW` decisions rather than an empty result. There
is no code path where a model is called and nothing was checked.

Layers, per docs/SPEC.md §8:

- **1, conventional validation** — size and shape, done here in `_check_size`.
- **2, provider moderation** — deliberately absent; see `MODERATION_NOTE`.
- **3, NeMo Guardrails** — the input and output rails, run on `safety-judge`.
- **4, Guardrails AI** — already present from Phase 3 for summaries.
- **5, Pydantic** — already present from Phase 3 for structured output.
- **6, human approval** — already present from Phase 3.

**Cost.** The NeMo rails are two extra model calls per chat request, on the cheap
alias. That is the price of the phase and it is worth naming: a conversation now
costs three calls, not one.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import Any, Final

from nemoguardrails import LLMRails, RailsConfig
from nemoguardrails.rails.llm.options import (
    GenerationLogOptions,
    GenerationOptions,
    GenerationRailsOptions,
)

from ai_core.models.gateway import gateway_key, gateway_url
from ai_core.safety.decisions import SafetyAction, SafetyDecision, SafetyOutcome, SafetyStage
from ai_core.safety.pii import describe, find_pii
from ai_core.telemetry import Attr, span

#: Bumped whenever `rails/vN.yml` changes. Recorded on every `safety_event`, so a
#: decision can always be traced to the rules that produced it.
POLICY_VERSION: Final = "safety_rails@1"

POLICY_SIZE: Final = "size_limit"
POLICY_PII: Final = "pii_scan"
POLICY_RAILS: Final = "nemo_rails"

#: Longest message accepted. Layer 1 of docs/SPEC.md §8, and the cheapest check
#: there is: it costs nothing and it runs before anything that costs money.
#: Generous, because pasting a stack trace or a config file is a normal thing to
#: ask about.
MAX_INPUT_CHARS: Final = 50_000

#: Why layer 2 is not implemented.
#:
#: Provider moderation endpoints are provider-specific — OpenAI's `/moderations`
#: has no equivalent behind every alias — so calling one directly would put a
#: provider name in application code and break CLAUDE.md invariant #2, which is
#: the one thing the gateway exists to prevent. Until LiteLLM exposes moderation
#: as an alias-addressable route, layer 3 covers the same ground through a model
#: we *can* address by role.
MODERATION_NOTE: Final = (
    "layer 2 (provider moderation) is intentionally absent: it cannot be reached "
    "through a LiteLLM alias, and reaching past the gateway would break invariant #2"
)

_RAILS_DIR = Path(__file__).parent / "rails"


@cache
def _rails() -> LLMRails:
    """The compiled rails, built once per process.

    Cached because loading parses YAML and constructs an LLM client; doing that
    per request would add latency to every message for no benefit. The gateway
    URL and key are substituted here rather than stored in the file, so the
    policy file names no host and carries no credential.
    """
    template = (_RAILS_DIR / "v1.yml").read_text(encoding="utf-8")
    yaml_content = template.replace("__GATEWAY_URL__", f"{gateway_url()}/v1").replace(
        "__GATEWAY_KEY__", gateway_key()
    )
    return LLMRails(RailsConfig.from_content(yaml_content=yaml_content))


def _rail_options(*, stage: SafetyStage) -> GenerationOptions:
    """Run one stage's rails and nothing else.

    Without this, NeMo would also *generate* an answer — duplicating work the
    chat graph already does, on the wrong model, and discarding the result. The
    log is requested because `activated_rails[].stop` is the explicit
    allow/block signal; inferring it by comparing the returned text against the
    input would be a string comparison standing in for a decision.
    """
    return GenerationOptions(
        rails=GenerationRailsOptions(
            input=stage is SafetyStage.INPUT,
            output=stage is SafetyStage.OUTPUT,
            dialog=False,
            retrieval=False,
        ),
        log=GenerationLogOptions(activated_rails=True),
    )


async def _run_rails(messages: list[dict[str, str]], stage: SafetyStage) -> SafetyDecision:
    """Ask NeMo whether this interaction may proceed.

    Its own span, unlike the size and PII checks: this one is a *model call* on
    the `safety-judge` alias, and it is the only part of a guardrail stage that
    costs money or takes measurable time. A trace that showed `input_guardrails`
    as one 900ms block would leave "why was that slow" unanswerable.
    """
    with span(POLICY_RAILS, {Attr.MODEL_ALIAS: "safety-judge", Attr.SPAN_KIND: "GUARDRAIL"}):
        return await _rails_verdict(messages, stage)


async def _rails_verdict(messages: list[dict[str, str]], stage: SafetyStage) -> SafetyDecision:
    try:
        result: Any = await _rails().generate_async(
            messages=messages, options=_rail_options(stage=stage)
        )
    except Exception as exc:
        # **Fail open, and say so.** A safety layer that is down must not take the
        # product down with it: refusing every message because the judge model is
        # unreachable turns a transient outage into a total one. The decision is
        # still recorded — as a warning, so the gap is visible in the audit rather
        # than silently absent.
        return SafetyDecision.refuse(
            stage,
            POLICY_RAILS,
            POLICY_VERSION,
            action=SafetyAction.ALLOW_WITH_WARNING,
            categories=["rails_unavailable"],
            explanation=f"safety rails could not run ({type(exc).__name__}); allowed unchecked",
        )

    stopped = [rail for rail in (result.log.activated_rails or []) if rail.stop]
    if not stopped:
        return SafetyDecision.allow(stage, POLICY_RAILS, POLICY_VERSION)

    return SafetyDecision.refuse(
        stage,
        POLICY_RAILS,
        POLICY_VERSION,
        action=SafetyAction.BLOCK,
        categories=[_category_for(rail.name) for rail in stopped],
        explanation=(
            "blocked by the "
            + ", ".join(rail.name for rail in stopped)
            + (" rail" if len(stopped) == 1 else " rails")
        ),
    )


def _category_for(rail_name: str) -> str:
    """A stable category from a rail's display name.

    NeMo names rails in prose ("self check input"); a `safety_event.categories`
    entry wants something a query can group by.
    """
    return re.sub(r"\W+", "_", rail_name.strip().lower())


def _check_size(text: str, stage: SafetyStage) -> SafetyDecision:
    if len(text) <= MAX_INPUT_CHARS:
        return SafetyDecision.allow(stage, POLICY_SIZE, POLICY_VERSION)
    return SafetyDecision.refuse(
        stage,
        POLICY_SIZE,
        POLICY_VERSION,
        action=SafetyAction.BLOCK,
        categories=["oversized"],
        explanation=f"message is {len(text)} characters; the limit is {MAX_INPUT_CHARS}",
    )


def _check_pii(text: str, stage: SafetyStage) -> SafetyDecision:
    categories = find_pii(text)
    if not categories:
        return SafetyDecision.allow(stage, POLICY_PII, POLICY_VERSION)
    return SafetyDecision.refuse(
        stage,
        POLICY_PII,
        POLICY_VERSION,
        # A warning, never a block — this is the user's own data, and refusing to
        # help them with it would be the wrong trade. See ai_core/safety/pii.py.
        action=SafetyAction.ALLOW_WITH_WARNING,
        categories=categories,
        explanation=describe(categories),
    )


async def check_input(text: str) -> SafetyOutcome:
    """Everything that runs before a question reaches a model.

    Ordered cheapest-first: size costs nothing, PII is a regex scan, and the rails
    are a model call. An oversized message is refused without paying for a judge.
    """
    size = _check_size(text, SafetyStage.INPUT)
    if size.blocks:
        return SafetyOutcome(stage=SafetyStage.INPUT, decisions=[size])

    pii = _check_pii(text, SafetyStage.INPUT)
    rails = await _run_rails([{"role": "user", "content": text}], SafetyStage.INPUT)
    return SafetyOutcome(stage=SafetyStage.INPUT, decisions=[size, pii, rails])


async def check_output(question: str, answer: str) -> SafetyOutcome:
    """Everything that runs before an answer reaches the user.

    The question is passed too because the output rail judges the answer *in
    context*: the same sentence can be a reasonable reply to one question and a
    non-sequitur to another.
    """
    pii = _check_pii(answer, SafetyStage.OUTPUT)
    rails = await _run_rails(
        [{"role": "user", "content": question}, {"role": "assistant", "content": answer}],
        SafetyStage.OUTPUT,
    )
    return SafetyOutcome(stage=SafetyStage.OUTPUT, decisions=[pii, rails])
