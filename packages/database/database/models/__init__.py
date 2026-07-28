"""ORM models for LearnTrail.

One module per aggregate, re-exported here so callers write
``from database.models import Chat`` and never depend on which file a model
lives in. Importing this package is what populates ``Base.metadata``, which is
why Alembic's env.py imports it explicitly (see migrations/env.py).

Two aggregates so far: the conversation (`chat`, `message`, Phase 1) and
knowledge (`summary_draft`, `learning`, `learning_revision`, Phase 3). The
remaining docs/SPEC.md §17 tables arrive with the phase that introduces their
concept: `safety_event` in Phase 4, `model_run` in Phase 5, `evaluation_*` in
Phase 6, `prompt_version` alongside the prompt lifecycle.

No model here has a `user_id`, and none ever will (CLAUDE.md invariant #1).
"""

from database.models.conversation import Chat, ChatStatus, Message, MessageRole
from database.models.knowledge import (
    ChangeSource,
    DraftStatus,
    Learning,
    LearningRevision,
    SafetyEvent,
    SummaryDraft,
)

__all__ = [
    "ChangeSource",
    "Chat",
    "ChatStatus",
    "DraftStatus",
    "Learning",
    "LearningRevision",
    "Message",
    "MessageRole",
    "SafetyEvent",
    "SummaryDraft",
]
