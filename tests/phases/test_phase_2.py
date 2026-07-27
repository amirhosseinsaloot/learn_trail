"""Phase 2 — LangGraph workflow

See docs/SPEC.md, "Phase 2 — LangGraph workflow" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
import uuid
from typing import Any

import pytest

#: The backend as published by docker-compose.yml. Over HTTP against the running
#: stack, because the criterion is about what a *chat request* leaves behind —
#: driving the graph directly would prove the graph works while saying nothing
#: about whether requests actually go through it.
API = "http://localhost:8000"

_NOT_RUNNING = (
    "the stack is not up — run `make up`. This says nothing about whether Phase 2 "
    "is built; it means the criterion could not be evaluated."
)


def _call(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(  # noqa: S310 - fixed http:// literal above
        f"{API}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - as above
        raw = response.read()
        return json.loads(raw) if raw else None


def _stream_answer(chat_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Drive the answer endpoint and collect its SSE events."""
    request = urllib.request.Request(  # noqa: S310 - fixed http:// literal above
        f"{API}/chats/{chat_id}/answer", data=b"", method="POST"
    )
    events: list[tuple[str, dict[str, Any]]] = []
    name = ""
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 - as above
        for raw_line in response:
            line = raw_line.decode().rstrip("\n")
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((name, json.loads(line.removeprefix("data: "))))
    return events


@pytest.mark.phase
def test_phase_2_exit_criterion() -> None:
    """Phase 2 — LangGraph workflow.

    Exit criterion (verbatim, docs/SPEC.md):

        "Each chat request is visible as a deterministic graph execution."

    Two claims, asserted separately because they can fail independently:

    **Visible.** After a real chat request, the checkpointer holds that request's
    execution, and replaying it names the nodes that ran. Visibility here is not
    a log line someone remembered to write — it is state the graph recorded
    itself.

    **Deterministic.** The nodes appear in exactly the order the graph declares.
    `NODE_SEQUENCE` is imported from the graph rather than copied here, so this
    test cannot drift into agreeing with itself while disagreeing with the code.

    **This one does call a model**, unlike the Phase 1 test. It cannot avoid it:
    the criterion is about what a chat request leaves behind, and a request that
    never reaches `generate_answer` leaves behind a different execution. Cost is
    bounded by asking for a single word on the cheapest alias.
    """
    from ai_core.graphs.chat import NODE_SEQUENCE

    try:
        _call("GET", "/chats")
    except (urllib.error.URLError, TimeoutError):
        pytest.skip(_NOT_RUNNING)

    chat = _call("POST", "/chats", {"title": "phase 2 exit criterion"})
    chat_id = chat["id"]
    try:
        _call("POST", f"/chats/{chat_id}/messages", {"content": "Reply with one short word."})

        events = _stream_answer(chat_id)
        names = [name for name, _ in events]
        assert "error" not in names, f"the request failed: {events}"
        assert names[-1] == "done", f"the answer never completed: {names[-3:]}"
        # It streamed rather than arriving in one lump — the graph emits tokens
        # on LangGraph's custom channel as `generate_answer` receives them.
        assert "token" in names

        done = dict(events[-1][1])
        # The alias, not a provider model: the graph's `choose_model` node picks
        # a role (CLAUDE.md invariant #2).
        assert done["alias"] == "learning-fast"

        executed = _executed_nodes(chat_id, sequence_number=int(done["sequence_number"]))

        # Visible: the request left an execution behind at all.
        assert executed, "the request left no graph execution in the checkpointer"
        # Deterministic: exactly the declared nodes, in the declared order.
        assert executed == list(NODE_SEQUENCE), (
            f"the request did not walk the declared graph: {executed} != {list(NODE_SEQUENCE)}"
        )
    finally:
        _purge(chat_id)


def _executed_nodes(chat_id: str, *, sequence_number: int) -> list[str]:
    """Replay the checkpointed execution for one request, oldest step first.

    The thread is `{chat_id}:{sequence_number}` — one per request, not per
    conversation. Threading by chat id alone re-feeds the previous turns into
    `add_messages`, which doubles the working context on every turn without
    erroring (see ai_core/graphs/checkpointer.py).
    """
    from langchain_core.runnables import RunnableConfig

    from ai_core.graphs.chat import build_chat_graph
    from ai_core.graphs.checkpointer import open_checkpointer

    async def run() -> list[str]:
        async with open_checkpointer() as checkpointer:
            graph = build_chat_graph().compile(checkpointer=checkpointer)
            config: RunnableConfig = {"configurable": {"thread_id": f"{chat_id}:{sequence_number}"}}
            history = [entry async for entry in graph.aget_state_history(config)]
            # Each entry's `next` names the node that was about to run, so
            # reading oldest-first replays the execution. `__start__` is
            # LangGraph's own entry marker, not one of our nodes.
            return [
                entry.next[0]
                for entry in reversed(history)
                if entry.next and not entry.next[0].startswith("__")
            ]

    return asyncio.run(run())


def _purge(chat_id: str) -> None:
    """Delete the chat this test created.

    Through the database rather than the API: the API only soft-deletes by
    design, so an API call would leave the row behind. LangGraph's checkpoint
    rows for the thread are left alone — they are the library's storage, outside
    our schema, and reaching into tables we do not own to tidy them would be
    worse than leaving a few rows.
    """
    from sqlalchemy import delete

    from database.models import Chat
    from database.session import engine, session_factory

    async def run() -> None:
        async with session_factory()() as db:
            await db.execute(delete(Chat).where(Chat.id == uuid.UUID(chat_id)))
            await db.commit()
        await engine().dispose()

    try:
        asyncio.run(run())
    except Exception as exc:  # pragma: no cover - cleanup must never mask a failure
        pytest.fail(f"could not clean up test chat {chat_id}: {exc}")
