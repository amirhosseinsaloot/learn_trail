"""Typed summary generation (docs/SPEC.md §7, Phase 3).

Pydantic AI implements the typed task; LangGraph owns the workflow. docs/SPEC.md
§7 is explicit that the two must not compete for orchestration, so there is no
graph here — this module exposes one async function that a graph node calls.

**What "typed" buys, and what it does not.** Pydantic AI asks the model for
output matching `LearningSummary` and re-prompts it when the result does not
validate. That fixes *shape*: missing fields, wrong types, unknown keys. It says
nothing about whether the content is faithful to the conversation, which is why
the summary graph runs validators after this and why nothing here is stored
without human approval (CLAUDE.md invariant #5).

The prompt is loaded from `prompts/`, not written here (docs/SPEC.md §12), and
the alias comes from the prompt file — so which model summarises is a property
of the prompt version, and both are recorded together on the draft.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import GatewayError, typed_model
from ai_core.prompt_library import Prompt, load_active
from ai_core.schemas.summary import LearningSummary

#: The prompt this task runs. Named once so the loader, the recorded
#: `prompt_version` and any future evaluation all refer to the same string.
PROMPT_NAME = "learning_summary"

#: How many times Pydantic AI may re-prompt when output fails validation.
#:
#: Two, not zero and not ten. Zero would make a single malformed response a user-
#: visible failure when a retry usually fixes it; a high number turns a model
#: that cannot satisfy the schema into a slow, expensive loop that fails anyway.
#: A retry is not free — it re-sends the whole transcript.
VALIDATION_RETRIES = 2


@dataclass(frozen=True)
class GeneratedSummary:
    """A validated draft, with the provenance needed to record it.

    The summary alone is not enough to persist: docs/SPEC.md §17 gives
    `summary_draft` a `prompt_version`, and from Phase 5 a `model_run` too.
    Returning them together means a caller cannot store the content while
    forgetting what produced it.
    """

    summary: LearningSummary
    #: e.g. `learning_summary@1` — the exact prompt text that produced this.
    prompt_version: str
    #: The alias requested (a role), not the provider model that served it.
    alias: ModelAlias


class SummaryGenerationError(RuntimeError):
    """The model could not produce a valid summary.

    Raised after retries are exhausted. Deliberately *not* a partial result: a
    summary that failed validation is the case the Phase 3 exit criterion is
    about, and returning it with a warning would put the burden of rejecting it
    on every caller.
    """


def _agent(prompt: Prompt, temperature: float | None = None) -> Agent[None, LearningSummary]:
    """Build the typed agent for a prompt version.

    Not cached: the agent closes over a model object, and caching one would
    outlive the event loop its underlying client belongs to. Construction is
    cheap — the expensive thing is the HTTP client, and that *is* shared.
    """
    alias = ModelAlias(prompt.model_settings.alias)
    return Agent(
        typed_model(alias),
        # `output_type` is what makes this typed generation rather than parsing
        # prose: Pydantic AI derives the schema from the model and enforces it.
        output_type=LearningSummary,
        instructions=prompt.template.system,
        retries=VALIDATION_RETRIES,
        # `temperature` is omitted entirely when None, for the reason
        # `CompletionRequest.temperature` documents: reasoning-tier models reject
        # it and the gateway runs with `drop_params: false`, so an explicit null
        # is an error rather than a no-op. Only the evaluation path sets it.
        model_settings=ModelSettings(
            max_tokens=prompt.model_settings.max_tokens,
            **({} if temperature is None else {"temperature": temperature}),
        ),
    )


async def summarise(transcript: str, *, temperature: float | None = None) -> GeneratedSummary:
    """Distil a conversation into a validated `LearningSummary`.

    Raises `SummaryGenerationError` if the model cannot produce output that
    satisfies the schema within the retry budget — which is the exit criterion's
    "malformed or incomplete summaries are rejected before persistence", enforced
    at the earliest point it can be.
    """
    prompt = load_active(PROMPT_NAME)
    alias = ModelAlias(prompt.model_settings.alias)

    try:
        result = await _agent(prompt, temperature).run(prompt.render_user(transcript=transcript))
    except GatewayError:
        # Already a domain error; let it through rather than relabelling a
        # transport failure as a generation failure.
        raise
    except Exception as exc:
        # Pydantic AI raises its own exception types for exhausted retries and
        # for unexpected model behaviour. Translating them here means callers —
        # and the graph node above — never import Pydantic AI to catch a failure,
        # the same boundary discipline the gateway applies to the provider SDK.
        raise SummaryGenerationError(
            f"{prompt.identifier}: the model did not produce a valid summary: {exc}"
        ) from exc

    return GeneratedSummary(summary=result.output, prompt_version=prompt.identifier, alias=alias)
