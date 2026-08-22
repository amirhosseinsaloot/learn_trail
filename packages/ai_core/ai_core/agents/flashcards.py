"""Generating flashcards from an approved Learning (docs/SPEC.md §15, Phase 12).

Mirrors the summariser (ai_core/agents/summariser.py): typed generation through
Pydantic AI against a gateway alias, so the model's output is validated into a
`FlashcardSet` rather than parsed from prose (CLAUDE.md invariant #4). The
difference is what the result *is* — a summary becomes a draft that can be
approved into knowledge; a flashcard set is a study aid returned and forgotten.
So there is no provenance to persist and no `model_run` obligation here beyond
what the endpoint chooses to record.

The provider SDK and Pydantic AI's own exception types stay behind this module,
exactly as they do for the summariser: a caller catches `FlashcardError` and
never imports either.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import GatewayError, typed_model
from ai_core.prompt_library import Prompt, load_active
from ai_core.schemas.flashcards import FlashcardSet

#: The prompt this task runs. Named once so the loader and any future evaluation
#: refer to the same string.
PROMPT_NAME = "flashcards"

#: Re-prompts allowed when output fails schema validation. Two, for the summariser's
#: reason: zero makes one malformed response a user-visible failure a retry would
#: fix; many turns a model that cannot satisfy the schema into a slow, costly loop.
VALIDATION_RETRIES = 2


class FlashcardError(RuntimeError):
    """The model could not produce a valid flashcard set.

    Raised after retries are exhausted. Not a partial set: a set that failed
    validation (too few cards, a front equal to its back, duplicate fronts) is
    not usable study material, and handing it back with a warning would put the
    burden of rejecting it on every caller.
    """


def _agent(prompt: Prompt) -> Agent[None, FlashcardSet]:
    """Build the typed agent for a prompt version. Not cached — see summariser."""
    alias = ModelAlias(prompt.model_settings.alias)
    return Agent(
        typed_model(alias),
        output_type=FlashcardSet,
        instructions=prompt.template.system,
        retries=VALIDATION_RETRIES,
        model_settings=ModelSettings(max_tokens=prompt.model_settings.max_tokens),
    )


async def generate_flashcards(learning: str) -> FlashcardSet:
    """Turn one approved Learning's rendered content into a validated set.

    Raises `FlashcardError` if the model cannot produce a set that satisfies the
    schema within the retry budget. The caller is expected to have already
    confirmed the Learning is approved and live — this function does not know
    what a Learning is, only that it was handed text to make cards from.
    """
    prompt = load_active(PROMPT_NAME)
    try:
        result = await _agent(prompt).run(prompt.render_user(learning=learning))
    except GatewayError:
        # Already a domain error; a transport failure is not a generation failure.
        raise
    except Exception as exc:
        raise FlashcardError(
            f"{prompt.identifier}: the model did not produce a valid flashcard set: {exc}"
        ) from exc
    return result.output
