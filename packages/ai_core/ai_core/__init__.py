"""LearnTrail AI application layer.

Middle of the docs/SPEC.md §16 layout: `ai_core` sits between `api` and
`database`. It imports neither — the dependency direction is one-way
(docs/ARCHITECTURE.md §7), and Phase 1's import-linter contracts will enforce
that rather than trust it.

What lives here as of Phase 1: the model aliases, the typed request/response
schemas, and the single sanctioned gateway client. `graphs/` (Phase 2),
`agents/` (Phase 3), `safety/` (Phase 4), `telemetry/` (Phase 5) and
`retrieval/` (Phase 8) are still empty, and each arrives with its phase.

There is no `prompts/` package here on purpose: prompt text is lifecycle-managed
*content* under the top-level `prompts/`, loaded as files and versioned through
`prompt_version` — not Python source to import.
"""

from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import GatewayError, answer, complete
from ai_core.schemas.completion import ChatTurn, CompletionRequest, CompletionResponse

__all__ = [
    "ChatTurn",
    "CompletionRequest",
    "CompletionResponse",
    "GatewayError",
    "ModelAlias",
    "answer",
    "complete",
]
