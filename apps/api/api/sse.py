"""Server-sent event framing.

SSE rather than websockets because the traffic is one-way — the server pushes an
answer, the client says nothing back — and SSE is plain HTTP: it survives proxies
that mangle upgrades, reconnects on its own, and needs no second protocol in the
stack. docs/ARCHITECTURE.md notes there are no websocket routes; this is why.

The wire format is three lines per event and unforgiving about all of them:

    event: <name>\\n
    data: <one line of JSON>\\n
    \\n

The blank line terminates the event, and a `data:` value containing a raw newline
silently splits into two events. `json.dumps` never emits a literal newline, so
routing every payload through this module is what keeps that true.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

#: `text/event-stream` is required — a browser's EventSource, and any spec-
#: compliant reader, ignores a stream served as anything else.
SSE_MEDIA_TYPE = "text/event-stream"

#: Sent alongside the media type. Without `no-cache` an intermediary is entitled
#: to buffer the whole response and hand it over at the end, which turns a
#: streamed answer into a slow non-streamed one — and looks like a code bug.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Nginx-specific and harmless elsewhere; nginx buffers proxied responses by
    # default, with the same symptom as above.
    "X-Accel-Buffering": "no",
}


def event(name: str, payload: BaseModel | dict[str, Any]) -> str:
    """Frame one named SSE event.

    Takes a Pydantic model or a plain dict so callers serialize through a schema
    rather than hand-building JSON — the same discipline as everywhere else on
    this boundary.
    """
    body = payload.model_dump_json() if isinstance(payload, BaseModel) else _dumps(payload)
    return f"event: {name}\ndata: {body}\n\n"


def _dumps(payload: dict[str, Any]) -> str:
    import json

    # `ensure_ascii` left at its default so non-ASCII escapes rather than
    # relying on the transport's encoding, and no `indent`: an indented payload
    # contains newlines, which would break the framing above.
    return json.dumps(payload)
