"""Domain error hierarchy.

Aggregates and domain services raise these; the API layer maps them once
(NU-018) using the ``code`` and ``http_status`` declared here, which follow
the stable codes in ARCHITECTURE.md section 6.
"""

from collections.abc import Mapping


class DomainError(Exception):
    """Base of every error a domain rule can raise."""

    code: str = "invalid_state"
    http_status: int = 409
    retryable: bool = False

    def __init__(self, message: str, *, details: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFound(DomainError):
    """The record does not exist for this owner; foreign ids answer the same way."""

    code = "not_found"
    http_status = 404


class InvalidState(DomainError):
    """The aggregate is not in a state that allows the operation."""

    code = "invalid_state"
    http_status = 409


class ValidationFailed(DomainError):
    """Input violates a domain limit; ``details`` may carry ``fields``."""

    code = "validation_failed"
    http_status = 422


class StaleRevision(DomainError):
    """The caller edited an older draft revision than the one stored."""

    code = "draft_stale"
    http_status = 409
