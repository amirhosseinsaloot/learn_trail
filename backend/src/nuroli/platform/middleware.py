"""Request ids and the per-request access line (ARCHITECTURE.md section 19).

Pure ASGI middleware so streamed responses are not buffered. Every HTTP
request gets a fresh id, exposed as ``request.state.request_id``, returned in
the ``X-Request-Id`` header, and included in the error envelope.
"""

import logging
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-Id"

log = logging.getLogger("nuroli.request")


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid7().hex
        state: dict[str, object] = scope.setdefault("state", {})
        state["request_id"] = request_id
        started = time.perf_counter()
        status = {"code": 0}

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = int(message["status"])
                headers = MutableHeaders(raw=message.setdefault("headers", []))
                headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            route = scope.get("route")
            log.info(
                "request",
                extra={
                    "request_id": request_id,
                    "user_id": state.get("user_id"),
                    "method": scope.get("method"),
                    "route": getattr(route, "path", None) or scope.get("path"),
                    "status": status["code"],
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
