"""Naming a conversation from its opening turns (docs/SPEC.md §6, Phase 1's
"Generating titles", built once the rest of the chat surface existed).

Mirrors the flashcard agent (ai_core/agents/flashcards.py): typed generation
through Pydantic AI against a gateway alias, so the title arrives validated
rather than parsed out of prose (CLAUDE.md invariant #4). Like flashcards and
unlike the summariser, there is no provenance to hand back — `chat` has no
`prompt_version` column, because a title is a label on a conversation and not
something an approved Learning is derived from.

Pydantic AI and the provider SDK stay behind this module: a caller catches
`TitleGenerationError` and imports neither.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import GatewayError, typed_model
from ai_core.prompt_library import Prompt, load_active
from ai_core.schemas.chat_title import ChatTitle

#: The prompt this task runs. Named once so the loader and any future evaluation
#: refer to the same string.
PROMPT_NAME = "chat_title"

#: Re-prompts allowed when output fails schema validation. Two, for the reason the
#: summariser documents — with the extra note that a retry here is cheap: the
#: input is a few opening turns, not a whole transcript.
VALIDATION_RETRIES = 2


class TitleGenerationError(RuntimeError):
    """The model could not produce a valid title.

    Raised after retries are exhausted, rather than falling back to something
    derived from the first message. A silent fallback would make "the titling
    model is broken" indistinguishable from "the titling model is working", and
    an untitled chat is a visible, harmless state the product already has.
    """


def _agent(prompt: Prompt) -> Agent[None, ChatTitle]:
    """Build the typed agent for a prompt version. Not cached — see summariser."""
    alias = ModelAlias(prompt.model_settings.alias)
    return Agent(
        typed_model(alias),
        output_type=ChatTitle,
        instructions=prompt.template.system,
        retries=VALIDATION_RETRIES,
        model_settings=ModelSettings(max_tokens=prompt.model_settings.max_tokens),
    )


async def generate_title(transcript: str) -> str:
    """Name a conversation from the rendered opening of its transcript.

    Takes text rather than messages for the same reason the other agents do:
    `ai_core` never sees a database row, so the caller decides how much of the
    conversation is worth spending on a title.

    Raises `TitleGenerationError` when the model cannot produce a title that
    satisfies the schema within the retry budget, and lets `GatewayError` through
    untouched — a transport failure is not a generation failure.
    """
    prompt = load_active(PROMPT_NAME)
    try:
        result = await _agent(prompt).run(prompt.render_user(transcript=transcript))
    except GatewayError:
        raise
    except Exception as exc:
        raise TitleGenerationError(
            f"{prompt.identifier}: the model did not produce a valid title: {exc}"
        ) from exc
    return result.output.title
