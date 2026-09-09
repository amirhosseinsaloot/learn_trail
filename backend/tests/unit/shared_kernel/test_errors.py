"""Domain errors carry the stable code and HTTP status from ARCHITECTURE.md section 6."""

import pytest

from nuroli.shared_kernel.errors import (
    DomainError,
    InvalidState,
    NotFound,
    StaleRevision,
    ValidationFailed,
)


@pytest.mark.parametrize(
    ("error_type", "code", "http_status"),
    [
        (NotFound, "not_found", 404),
        (InvalidState, "invalid_state", 409),
        (ValidationFailed, "validation_failed", 422),
        (StaleRevision, "draft_stale", 409),
    ],
)
def test_error_declares_code_and_http_status(
    error_type: type[DomainError], code: str, http_status: int
) -> None:
    error = error_type("explained in prose")
    assert isinstance(error, DomainError)
    assert error.code == code
    assert error.http_status == http_status
    assert error.message == "explained in prose"
    assert str(error) == "explained in prose"
    assert error.retryable is False


def test_details_default_to_none_and_are_kept_when_given() -> None:
    assert NotFound("gone").details is None
    error = ValidationFailed("bad input", details={"fields": [{"field": "title"}]})
    assert error.details == {"fields": [{"field": "title"}]}


def test_every_domain_error_is_catchable_as_domain_error() -> None:
    with pytest.raises(DomainError):
        raise StaleRevision("revision 3 is behind 4")
