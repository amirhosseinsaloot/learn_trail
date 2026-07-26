"""Contract for the SSE framing helpers.

Pure string formatting, so no database and no model. Worth testing at all because
the wire format is unforgiving in ways that fail *silently*: a stray newline
inside a `data:` value splits one event into two, and a reader sees a truncated
JSON payload rather than an error.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from api import sse


class _Payload(BaseModel):
    text: str


def test_event_has_the_three_part_frame() -> None:
    frame = sse.event("token", _Payload(text="hi"))
    assert frame == 'event: token\ndata: {"text":"hi"}\n\n'


def test_event_terminates_with_a_blank_line() -> None:
    # The blank line is what tells a reader the event is complete. Without it the
    # reader waits for more, and the last event of a stream never arrives.
    assert sse.event("done", {"ok": True}).endswith("\n\n")


def test_multiline_content_does_not_break_the_frame() -> None:
    """The failure this guards is silent, which is why it is asserted.

    A literal newline in a `data:` value ends that line, so the remainder is
    parsed as a new field — the consumer gets truncated JSON. JSON encoding
    escapes newlines to `\\n`, keeping the payload on one line.
    """
    frame = sse.event("token", _Payload(text="line one\nline two"))

    body = [line for line in frame.split("\n") if line.startswith("data: ")]
    assert len(body) == 1, "payload must occupy exactly one data: line"
    assert json.loads(body[0][6:])["text"] == "line one\nline two"


def test_dict_payloads_are_json_encoded() -> None:
    frame = sse.event("done", {"message_id": "abc", "input_tokens": 3})
    assert json.loads(frame.split("data: ")[1]) == {"message_id": "abc", "input_tokens": 3}


def test_media_type_is_exactly_what_readers_require() -> None:
    # A stream served as application/json or text/plain is ignored by EventSource
    # and by any spec-compliant reader.
    assert sse.SSE_MEDIA_TYPE == "text/event-stream"


def test_headers_defeat_intermediary_buffering() -> None:
    """Without these an intermediary may buffer the whole response and deliver it
    at the end — which turns a streamed answer into a slow non-streamed one and
    looks exactly like a bug in the application."""
    assert sse.SSE_HEADERS["Cache-Control"] == "no-cache"
    assert sse.SSE_HEADERS["X-Accel-Buffering"] == "no"
