"""Structured logging with redaction (ARCHITECTURE.md sections 17 and 19).

JSON lines for Compose and production, text for development. Every record
passes through ``redact``: configured secret values, bearer tokens, key and
password assignments, and email addresses beyond their first two characters
are replaced before anything reaches stdout.
"""

import json
import logging
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from nuroli.platform.settings import Settings

REDACTED = "***"
_EMAIL = re.compile(r"\b([A-Za-z0-9._%+-]{2})[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT = re.compile(
    r"(?i)\b((?:api[_-]?key|access[_-]?token|token|secret(?:[_-]?key)?|password|authorization)"
    r"['\"]?\s*[=:]\s*['\"]?)(?:bearer\s+)?[^\s'\",;]+"
)
# Attributes every LogRecord carries; anything else came from ``extra``.
_STANDARD_ATTRIBUTES = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    text = _ASSIGNMENT.sub(rf"\1{REDACTED}", text)
    text = _BEARER.sub(rf"\1{REDACTED}", text)
    return _EMAIL.sub(rf"\1{REDACTED}", text)


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {key: value for key, value in record.__dict__.items() if key not in _STANDARD_ATTRIBUTES}


class RedactingFormatter(logging.Formatter):
    def __init__(self, secrets: Sequence[str]) -> None:
        super().__init__()
        self._secrets = list(secrets)

    def fields(self, record: logging.LogRecord) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": redact(record.getMessage(), self._secrets),
        }
        for key, value in _extras(record).items():
            fields[key] = redact(value, self._secrets) if isinstance(value, str) else value
        if record.exc_info:
            fields["exception"] = redact(self.formatException(record.exc_info), self._secrets)
        return fields


class JsonFormatter(RedactingFormatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(self.fields(record), default=str, ensure_ascii=False)


class TextFormatter(RedactingFormatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = self.fields(record)
        time, level = fields.pop("time"), fields.pop("level")
        head = f"{time} {level:<7} {fields.pop('logger')}: {fields.pop('message')}"
        exception = fields.pop("exception", None)
        tail = " ".join(f"{key}={value}" for key, value in fields.items())
        line = f"{head} {tail}".rstrip()
        return f"{line}\n{exception}" if exception else line


def configure_logging(settings: Settings) -> None:
    """Route every logger to stdout through the redacting formatter."""
    formatter: RedactingFormatter = (
        JsonFormatter(settings.secret_values())
        if settings.log_format == "json"
        else TextFormatter(settings.secret_values())
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    for name in ("uvicorn", "uvicorn.error"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
    # The request-id middleware writes the access line with route and request id.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
