"""Phase 1 — Basic AI chat

See docs/SPEC.md, "Phase 1 — Basic AI chat" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any

import pytest

#: The backend as published by docker-compose.yml. Deliberately over HTTP against
#: the *running stack* rather than an in-process ASGI client: an in-process app
#: cannot be stopped and restarted, and stopping and restarting is the entire
#: criterion.
API = "http://localhost:8000"

#: The service to bounce. Only the backend — restarting Postgres too would prove
#: something stronger than the criterion asks and would make this test slow
#: enough that people stop running `make status`.
BACKEND_SERVICE = "backend"

_NOT_RUNNING = (
    "the stack is not up — run `make up`. This says nothing about whether Phase 1 "
    "is built; it means the criterion could not be evaluated."
)


def _docker() -> str:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker CLI not found — this criterion is about restarting the application")
    return docker


def _call(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(  # noqa: S310 - fixed http:// literal above
        f"{API}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - as above
        raw = response.read()
        return json.loads(raw) if raw else None


def _restart_backend() -> None:
    """Stop the application and start it again — literally.

    `stop` then `up -d --wait`, not `restart`: `--wait` blocks until the
    healthcheck passes, so the assertions below run against a process that is
    genuinely serving rather than one that has merely been launched.
    """
    docker = _docker()
    subprocess.run(  # noqa: S603 - fixed argv, binary from shutil.which
        [docker, "compose", "stop", BACKEND_SERVICE],
        capture_output=True,
        check=True,
        timeout=120,
    )
    subprocess.run(  # noqa: S603 - as above
        [docker, "compose", "up", "-d", "--wait", "--wait-timeout", "120", BACKEND_SERVICE],
        capture_output=True,
        check=True,
        timeout=180,
    )


@pytest.mark.phase
def test_phase_1_exit_criterion() -> None:
    """Phase 1 — Basic AI chat.

    Exit criterion (verbatim, docs/SPEC.md):

        "You can stop the application, restart it and continue a previous conversation."

    Asserted in three beats, mirroring the sentence: hold a conversation, stop
    and restart the application, then continue that same conversation.

    **No model call.** The criterion is about a conversation surviving a restart,
    not about answer quality — and this test runs on every `make status`, so a
    model call here would bill the user for checking where the project is. The
    live model path is covered by the `slow`-marked test in packages/ai_core and
    by the endpoint tests in apps/api.

    "Continue" is asserted as more than "read back": after the restart the test
    appends another turn and checks the new process assigned the *next*
    sequence number. That number cannot be guessed without reading the prior
    transcript out of storage, so it is the property that would break if any part
    of the conversation had been held in memory.
    """
    try:
        _call("GET", "/chats")
    except (urllib.error.URLError, TimeoutError):
        pytest.skip(_NOT_RUNNING)

    # --- 1. hold a conversation ------------------------------------------------
    chat = _call("POST", "/chats", {"title": "phase 1 exit criterion"})
    chat_id = chat["id"]
    try:
        for text in ("first question", "second question"):
            _call("POST", f"/chats/{chat_id}/messages", {"content": text})

        before = _call("GET", f"/chats/{chat_id}")
        assert [m["content"] for m in before["messages"]] == ["first question", "second question"]

        # --- 2. stop the application and restart it ----------------------------
        _restart_backend()

        # --- 3. continue that previous conversation ----------------------------
        after = _call("GET", f"/chats/{chat_id}")
        assert after["id"] == chat_id
        assert after["title"] == "phase 1 exit criterion"
        assert [m["content"] for m in after["messages"]] == ["first question", "second question"], (
            "the conversation did not survive the restart"
        )
        # Message identity, not just text: the same rows came back, rather than
        # anything having been re-created.
        assert [m["id"] for m in after["messages"]] == [m["id"] for m in before["messages"]]

        appended = _call("POST", f"/chats/{chat_id}/messages", {"content": "a follow-up"})
        assert appended["sequence_number"] == 2, (
            "the restarted application did not continue the conversation — it assigned "
            f"position {appended['sequence_number']} instead of 2, so it was not reading "
            "the existing transcript"
        )

        final = _call("GET", f"/chats/{chat_id}")
        assert [m["content"] for m in final["messages"]] == [
            "first question",
            "second question",
            "a follow-up",
        ]
    finally:
        # Leave no trace: this runs on every `make status`, and a status command
        # that slowly fills the database with its own test chats is a status
        # command people stop trusting.
        _purge(chat_id)


def _purge(chat_id: str) -> None:
    """Hard-delete the chat this test created.

    Goes to the database rather than the API on purpose: the API only ever
    soft-deletes (docs/SPEC.md §6 makes deletion restorable), so an API call
    would leave the row behind by design. Messages go with it via
    `ON DELETE CASCADE`.
    """
    import asyncio

    from sqlalchemy import delete

    from database.models import Chat
    from database.session import engine, session_factory

    async def run() -> None:
        async with session_factory()() as db:
            await db.execute(delete(Chat).where(Chat.id == chat_id))
            await db.commit()
        await engine().dispose()

    try:
        asyncio.run(run())
    except Exception as exc:  # pragma: no cover - cleanup must never mask a failure
        pytest.fail(f"could not clean up test chat {chat_id}: {exc}")
