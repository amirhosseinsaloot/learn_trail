"""ORM models for LearnTrail.

One module per aggregate, re-exported here so callers write
``from database.models import Chat`` and never depend on which file a model
lives in. Importing this package is what populates ``Base.metadata``, which is
why Alembic's env.py imports it explicitly (see migrations/env.py).

Phase 1 ships the conversation aggregate only — `chat` and `message`. The
remaining tables in docs/SPEC.md §17 arrive with the phase that introduces their
concept: `summary_draft`/`learning`/`learning_revision` in Phase 3,
`safety_event` in Phase 4, `model_run` in Phase 5, `evaluation_*` in Phase 6,
`prompt_version` alongside the prompt lifecycle.

No model here has a `user_id`, and none ever will (CLAUDE.md invariant #1).
"""

from database.models.conversation import Chat, ChatStatus, Message, MessageRole

__all__ = ["Chat", "ChatStatus", "Message", "MessageRole"]
