"""Redaction and structured formatting (ARCHITECTURE.md sections 17 and 19)."""

import json
import logging

import pytest

from nuroli.platform.logging import JsonFormatter, TextFormatter, configure_logging, redact
from nuroli.platform.settings import load_settings


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("user amirhosseinsaloot@gmail.com signed in", "user am*** signed in"),
        ("contact: a.b@example.co.uk", "contact: a.***"),
        ("Authorization: Bearer sk-live-abcdef123456", "Authorization: ***"),
        ("sent bearer sk-live-abcdef123456 header", "sent bearer *** header"),
        ("api_key=tvly-12345 sent", "api_key=*** sent"),
        ('{"password": "hunter2"}', '{"password": "***"}'),
        ("token: abc.def-ghi", "token: ***"),
        ("nothing sensitive here", "nothing sensitive here"),
    ],
)
def test_redact_masks_emails_tokens_and_assignments(text: str, expected: str) -> None:
    assert redact(text) == expected


def test_redact_replaces_configured_secret_values() -> None:
    assert (
        redact("dsn postgresql+asyncpg://u:p4ss@db/x", ["p4ss"])
        == "dsn postgresql+asyncpg://u:***@db/x"
    )


def record(message: str, **extra: object) -> logging.LogRecord:
    entry = logging.LogRecord("nuroli.test", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(entry, key, value)
    return entry


def test_json_formatter_emits_one_object_with_extras_redacted() -> None:
    formatter = JsonFormatter(["s3cret"])
    line = formatter.format(
        record(
            "model call by amir@example.org",
            request_id="abc",
            model_host="api.example",
            key="s3cret",
        )
    )
    payload = json.loads(line)
    assert payload["level"] == "info"
    assert payload["logger"] == "nuroli.test"
    assert payload["message"] == "model call by am***"
    assert payload["request_id"] == "abc"
    assert payload["model_host"] == "api.example"
    assert payload["key"] == "***"
    assert payload["time"].endswith("+00:00")


def test_text_formatter_is_one_line_with_key_values() -> None:
    line = TextFormatter([]).format(record("started", model_name="fake-model"))
    assert line.endswith("nuroli.test: started model_name=fake-model")
    assert "\n" not in line


def test_exception_text_is_redacted() -> None:
    formatter = JsonFormatter(["p4ss"])
    try:
        raise RuntimeError("connect failed with password p4ss")
    except RuntimeError:
        entry = record("boom")
        entry.exc_info = __import__("sys").exc_info()
    payload = json.loads(formatter.format(entry))
    assert "p4ss" not in payload["exception"]
    assert "RuntimeError" in payload["exception"]


def test_configure_logging_redacts_settings_secrets_in_captured_output(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NUROLI_MODEL_API_KEY", "sk-test-only-model-key")
    monkeypatch.setenv("NUROLI_LOG_LEVEL", "info")
    settings = load_settings()
    configure_logging(settings)
    logging.getLogger("nuroli.test").info(
        "calling model with key sk-test-only-model-key for amirhosseinsaloot@gmail.com",
        extra={"database": settings.database_url.get_secret_value()},
    )
    captured = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(captured)
    assert "sk-test-only-model-key" not in captured
    assert "test-only-db-password" not in captured
    assert "amirhosseinsaloot" not in captured
    assert payload["message"] == "calling model with key *** for am***"
    assert payload["database"] == "***", "the whole DSN is a configured secret"
