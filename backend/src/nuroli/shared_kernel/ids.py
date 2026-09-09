"""Typed identifiers. UUIDv7 generated in the application (R-24, R-28)."""

import uuid
from typing import NewType

UserId = NewType("UserId", uuid.UUID)
SessionId = NewType("SessionId", uuid.UUID)
ConversationId = NewType("ConversationId", uuid.UUID)
MessageId = NewType("MessageId", uuid.UUID)
SummaryId = NewType("SummaryId", uuid.UUID)
SummaryVersionId = NewType("SummaryVersionId", uuid.UUID)


def new_id() -> uuid.UUID:
    """Time-ordered id; wrap it in the aggregate's NewType at the call site."""
    return uuid.uuid7()
