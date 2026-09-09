"""JSON error envelope (ARCHITECTURE.md section 6, R-24).

Every error response has the shape ``{"error": {"code", "message", "details",
"retryable"}}``. This skeleton covers validation, routing, and unexpected
failures without exposing a stack trace; NU-018 adds the domain-error table.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException

_CODES_BY_STATUS: dict[int, str] = {
    status.HTTP_401_UNAUTHORIZED: "unauthenticated",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "not_found",
    status.HTTP_413_CONTENT_TOO_LARGE: "payload_too_large",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_failed",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
}


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
    request_id: str | None = None,
) -> JSONResponse:
    """Build the envelope; the request id, when known, travels in the header too."""
    headers = {"X-Request-Id": request_id} if request_id else None
    body = {"error": {"code": code, "message": message, "details": details, "retryable": retryable}}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def request_id_of(request: Request) -> str | None:
    """Request id set by the request-id middleware (NU-009); None before it exists."""
    return getattr(request.state, "request_id", None)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_failed",
            message="The request did not pass validation.",
            details={"fields": fields},
            request_id=request_id_of(request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def on_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODES_BY_STATUS.get(exc.status_code, "internal_error")
        if exc.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR and code == "internal_error":
            code = "request_rejected"
        return error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
            request_id=request_id_of(request),
        )

    @app.exception_handler(Exception)
    async def on_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = request_id_of(request)
        return error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Something went wrong on the server. Retry, quoting the request id.",
            details={"request_id": request_id} if request_id else None,
            request_id=request_id,
        )
