"""Behavioural contract for the chat and message endpoints.

Exercised through the real ASGI app against a real Postgres — no mocked session,
no fake repository. What these endpoints do *is* read and write rows under
constraints, so a test double would assert that the handler calls the methods we
wrote rather than that the behaviour is right.

Skips (never fails) when no database is reachable, so `make test` stays runnable
with the stack down. Run `make up` to exercise them.

Isolation: each test runs inside an outer transaction that the fixture rolls
back. The handlers under test call `commit()` — which is the point, since
"restart and resume" is meaningless without one — so the session is bound to that
outer transaction with SQLAlchemy's default `conditional_savepoint` join mode: a
handler's commit releases a savepoint and the outer rollback still discards
everything.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_core.graphs.chat import build_chat_graph
from ai_core.safety.decisions import SafetyAction, SafetyDecision, SafetyOutcome, SafetyStage
from api.main import app
from database.models import Message, ModelRun, SafetyEvent
from database.session import engine, session

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db(anyio_backend: str) -> AsyncIterator[AsyncSession]:
    """The one session the whole test shares, on a transaction that is rolled back.

    Exposed as its own fixture so a test can read back what a request wrote —
    `safety_event` rows are written by the graph, never returned by an endpoint,
    so asserting on them means querying the same transaction the handler used.
    """
    try:
        connection = await engine().connect()
    except DBAPIError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no database reachable ({type(exc).__name__}) — run `make up`")

    transaction = await connection.begin()
    test_session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield test_session
    finally:
        await test_session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


@pytest.fixture
async def client(db: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired to the app, sharing one rolled-back transaction."""

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db

    # The override is what keeps the handlers on this transaction. Without it
    # they would open their own sessions against the engine, commit for real, and
    # leave rows behind.
    app.dependency_overrides[session] = override_session
    # The real graph, compiled with an in-memory checkpointer. Phase 2 made the
    # graph the request path, so a stubbed graph would leave these tests
    # asserting nothing about how a request is actually served. Postgres
    # checkpointing is exercised by the Phase 2 exit-criterion test; here the
    # database is real but the checkpoint store need not be.
    app.state.chat_graph = build_chat_graph().compile(checkpointer=InMemorySaver())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://learntrail.test"
        ) as http:
            yield http
    finally:
        app.dependency_overrides.clear()


async def _new_chat(client: AsyncClient, title: str | None = "A chat") -> dict[str, object]:
    response = await client.post("/chats", json={"title": title})
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


# --- creating -----------------------------------------------------------------


async def test_creates_a_chat_active_and_empty(client: AsyncClient) -> None:
    chat = await _new_chat(client, "Learning SQL")

    assert chat["title"] == "Learning SQL"
    assert chat["status"] == "active"
    assert chat["deleted_at"] is None
    # ChatDetail, not ChatRead: a client can render the empty conversation
    # straight from the create response.
    assert chat["messages"] == []


async def test_creates_an_untitled_chat(client: AsyncClient) -> None:
    chat = await _new_chat(client, None)
    assert chat["title"] is None


@pytest.mark.parametrize("title", ["", "   "])
async def test_rejects_a_blank_title_with_422_not_500(client: AsyncClient, title: str) -> None:
    """The schema catches this, so it is a 422 naming the field.

    Without the schema constraint the database's `ck_chat_title_not_blank` would
    still refuse it — but as an unhandled IntegrityError, i.e. a 500. The
    constraint is the backstop; this is the interface.
    """
    response = await client.post("/chats", json={"title": title})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "title"]


async def test_a_client_cannot_choose_the_chat_id(client: AsyncClient) -> None:
    # Unknown fields are ignored rather than honoured: `id` is server-owned.
    forged = "00000000-0000-0000-0000-000000000000"
    chat = (await client.post("/chats", json={"title": "x", "id": forged})).json()
    assert chat["id"] != forged


# --- listing ------------------------------------------------------------------


async def test_lists_most_recently_active_first(client: AsyncClient) -> None:
    first = await _new_chat(client, "older")
    second = await _new_chat(client, "newer")
    # Activity, not creation, is what orders the list — so touching the older
    # chat must move it to the front.
    await client.post(f"/chats/{first['id']}/messages", json={"content": "ping"})

    listed = (await client.get("/chats")).json()
    ids = [chat["id"] for chat in listed]
    assert ids.index(first["id"]) < ids.index(second["id"])


async def test_listing_hides_deleted_chats_unless_asked(client: AsyncClient) -> None:
    kept = await _new_chat(client, "kept")
    removed = await _new_chat(client, "removed")
    assert (await client.delete(f"/chats/{removed['id']}")).status_code == 204

    default_ids = {chat["id"] for chat in (await client.get("/chats")).json()}
    assert removed["id"] not in default_ids
    assert kept["id"] in default_ids

    with_deleted = await client.get("/chats", params={"include_deleted": True})
    assert removed["id"] in {chat["id"] for chat in with_deleted.json()}


# --- resuming -----------------------------------------------------------------


async def test_unknown_chat_is_404(client: AsyncClient) -> None:
    response = await client.get("/chats/11111111-2222-3333-4444-555555555555")
    assert response.status_code == 404


async def test_malformed_chat_id_is_422_not_404(client: AsyncClient) -> None:
    # A non-UUID path segment is a malformed request, not a missing resource.
    assert (await client.get("/chats/not-a-uuid")).status_code == 422


async def test_resume_returns_the_transcript_in_order(client: AsyncClient) -> None:
    """The Phase 1 exit criterion in miniature: the conversation is readable
    back out of the database, in the order it happened."""
    chat = await _new_chat(client)
    for content in ("first", "second", "third"):
        response = await client.post(f"/chats/{chat['id']}/messages", json={"content": content})
        assert response.status_code == 201, response.text

    detail = (await client.get(f"/chats/{chat['id']}")).json()
    assert [m["content"] for m in detail["messages"]] == ["first", "second", "third"]
    assert [m["sequence_number"] for m in detail["messages"]] == [0, 1, 2]


# --- renaming -----------------------------------------------------------------


async def test_renames_a_chat(client: AsyncClient) -> None:
    chat = await _new_chat(client, "before")
    renamed = await client.patch(f"/chats/{chat['id']}", json={"title": "after"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "after"
    assert (await client.get(f"/chats/{chat['id']}")).json()["title"] == "after"


async def test_rename_requires_a_title(client: AsyncClient) -> None:
    # Omitting it is a client error, not an instruction to clear the title —
    # setting one is this endpoint's entire purpose.
    chat = await _new_chat(client)
    assert (await client.patch(f"/chats/{chat['id']}", json={})).status_code == 422


# --- deleting and restoring ---------------------------------------------------


async def test_soft_delete_keeps_the_chat_readable(client: AsyncClient) -> None:
    chat = await _new_chat(client)
    await client.post(f"/chats/{chat['id']}/messages", json={"content": "still here"})

    assert (await client.delete(f"/chats/{chat['id']}")).status_code == 204

    # Still fetchable — it is restorable, so 404 here would make restore
    # impossible and would misreport "deleted" as "never existed".
    deleted = (await client.get(f"/chats/{chat['id']}")).json()
    assert deleted["status"] == "deleted"
    assert deleted["deleted_at"] is not None
    assert [m["content"] for m in deleted["messages"]] == ["still here"]


async def test_delete_is_idempotent_and_preserves_the_original_timestamp(
    client: AsyncClient,
) -> None:
    chat = await _new_chat(client)
    await client.delete(f"/chats/{chat['id']}")
    first_deleted_at = (await client.get(f"/chats/{chat['id']}")).json()["deleted_at"]

    assert (await client.delete(f"/chats/{chat['id']}")).status_code == 204

    # A retried DELETE must not rewrite when the deletion happened.
    assert (await client.get(f"/chats/{chat['id']}")).json()["deleted_at"] == first_deleted_at


async def test_restore_clears_both_lifecycle_columns(client: AsyncClient) -> None:
    chat = await _new_chat(client)
    await client.delete(f"/chats/{chat['id']}")

    restored = await client.post(f"/chats/{chat['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    # Both columns move together or the CHECK constraint would have refused the
    # commit — asserting the pair is asserting the invariant, not two fields.
    assert restored.json()["deleted_at"] is None


async def test_restore_is_idempotent_on_an_active_chat(client: AsyncClient) -> None:
    chat = await _new_chat(client)
    response = await client.post(f"/chats/{chat['id']}/restore")
    assert response.status_code == 200
    assert response.json()["status"] == "active"


# --- appending messages -------------------------------------------------------


async def test_appended_messages_are_always_from_the_user(client: AsyncClient) -> None:
    """A client may only append its own turn.

    From Phase 3 an approved Learning is derived from this transcript, so a
    forged assistant turn would be a route to laundering model output past the
    human approval gate (CLAUDE.md invariant #5). `role` is not in the schema, so
    sending it is ignored rather than honoured.
    """
    chat = await _new_chat(client)
    response = await client.post(
        f"/chats/{chat['id']}/messages",
        json={"content": "I am not the assistant", "role": "assistant", "sequence_number": 99},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "user"
    assert body["sequence_number"] == 0


async def test_rejects_empty_message_content(client: AsyncClient) -> None:
    chat = await _new_chat(client)
    for content in ("", "   "):
        response = await client.post(f"/chats/{chat['id']}/messages", json={"content": content})
        assert response.status_code == 422, content


async def test_appending_to_a_deleted_chat_is_409_not_404(client: AsyncClient) -> None:
    """409, because the chat exists and the request is refused for a reason the
    caller can act on — restore it. A 404 would say "no such chat", which is
    both false and unactionable."""
    chat = await _new_chat(client)
    await client.delete(f"/chats/{chat['id']}")

    response = await client.post(f"/chats/{chat['id']}/messages", json={"content": "hello"})
    assert response.status_code == 409
    assert "restore" in response.json()["detail"]


async def test_appending_to_an_unknown_chat_is_404(client: AsyncClient) -> None:
    response = await client.post(
        "/chats/11111111-2222-3333-4444-555555555555/messages", json={"content": "hello"}
    )
    assert response.status_code == 404


async def test_appending_a_message_counts_as_activity_on_the_chat(client: AsyncClient) -> None:
    """Inserting a child row does not update the parent, so the column's
    `onupdate` never fires — the handler issues an explicit UPDATE. Without it
    the chat list's ordering would silently reflect creation, not activity."""
    chat = await _new_chat(client)
    before = (await client.get(f"/chats/{chat['id']}")).json()["updated_at"]

    await client.post(f"/chats/{chat['id']}/messages", json={"content": "activity"})

    after = (await client.get(f"/chats/{chat['id']}")).json()["updated_at"]
    assert after > before


async def test_no_response_body_mentions_a_user(client: AsyncClient) -> None:
    """CLAUDE.md invariant #1 at the wire level.

    `role: "user"` is a message author label, not an identity — hence the check
    for id-shaped keys rather than the substring.
    """
    chat = await _new_chat(client)
    await client.post(f"/chats/{chat['id']}/messages", json={"content": "hi"})
    detail = (await client.get(f"/chats/{chat['id']}")).json()

    forbidden = {"user_id", "userId", "owner", "owner_id", "author_id", "account_id"}
    assert not (forbidden & set(detail))
    assert all(not (forbidden & set(message)) for message in detail["messages"])


# --- streaming an answer -------------------------------------------------------
#
# The gateway is stubbed rather than called. These tests are about the endpoint's
# contract — what it validates, what it persists, what it emits — and a real model
# would make them slow, non-deterministic and paid. The live model path is covered
# by the `slow`-marked test in packages/ai_core.


@pytest.fixture(autouse=True)
def _allow_safety(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both safety checks pass, unless a test stubs them otherwise.

    Autouse and unconditional: the checks sit on the default path from Phase 4 and
    each is a real judge-model call. Left unstubbed they would make every endpoint
    test paid, slow and dependent on the gateway being reachable — and because the
    rails fail *open*, an unreachable judge would not even fail loudly, it would
    quietly turn these into tests of the fail-open path.
    """
    _stub_safety(monkeypatch)


def _stub_safety(
    monkeypatch: pytest.MonkeyPatch,
    *,
    on_input: SafetyAction = SafetyAction.ALLOW,
    on_output: SafetyAction = SafetyAction.ALLOW,
) -> None:
    from ai_core.graphs import chat as chat_graph_module

    def outcome(stage: SafetyStage, action: SafetyAction) -> SafetyOutcome:
        if action is SafetyAction.ALLOW:
            return SafetyOutcome(stage=stage, decisions=[SafetyDecision.allow(stage, "stub", "v1")])
        return SafetyOutcome(
            stage=stage,
            decisions=[
                SafetyDecision.refuse(
                    stage,
                    "stub",
                    "v1",
                    action=action,
                    categories=["testing"],
                    explanation=f"stubbed {action.value}",
                )
            ],
        )

    async def fake_input(text: str) -> SafetyOutcome:
        return outcome(SafetyStage.INPUT, on_input)

    async def fake_output(question: str, answer: str) -> SafetyOutcome:
        return outcome(SafetyStage.OUTPUT, on_output)

    monkeypatch.setattr(chat_graph_module, "check_input", fake_input)
    monkeypatch.setattr(chat_graph_module, "check_output", fake_output)


def _stub_stream(
    monkeypatch: pytest.MonkeyPatch,
    *,
    parts: list[str],
    finish_reason: str = "stop",
    error: Exception | None = None,
) -> None:
    """Replace the gateway stream with a scripted one."""
    from ai_core import CompletionResponse, FinalChunk, ModelAlias, TokenChunk
    from ai_core.graphs import chat as chat_graph_module

    async def fake_stream(request: object) -> AsyncIterator[object]:
        for part in parts:
            yield TokenChunk(text=part)
        if error is not None:
            raise error
        yield FinalChunk(
            response=CompletionResponse(
                alias=ModelAlias.LEARNING_FAST,
                provider_model="stub-model",
                text="".join(parts),
                input_tokens=7,
                output_tokens=len(parts),
                finish_reason=finish_reason,
            )
        )

    # Patched on the graph module: `generate_answer` is what calls the gateway
    # now, so patching the router would replace a name nothing reads.
    monkeypatch.setattr(chat_graph_module, "stream", fake_stream)


def _parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    """Parse a raw SSE body into (event name, payload) pairs."""
    events: list[tuple[str, dict[str, object]]] = []
    name = ""
    for line in body.splitlines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            events.append((name, json.loads(line.removeprefix("data: "))))
    return events


async def _ask(client: AsyncClient, chat_id: str, question: str = "why?") -> None:
    response = await client.post(f"/chats/{chat_id}/messages", json={"content": question})
    assert response.status_code == 201, response.text


async def test_streams_tokens_then_persists_the_answer(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_stream(monkeypatch, parts=["Because ", "it ", "streams."])
    chat = await _new_chat(client)
    await _ask(client, str(chat["id"]))

    response = await client.post(f"/chats/{chat['id']}/answer")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    assert [name for name, _ in events] == ["token", "token", "token", "done"]

    # The answer is persisted as a real assistant turn, positioned after the
    # question — this is what makes it survive a restart.
    detail = (await client.get(f"/chats/{chat['id']}")).json()
    assert [(m["role"], m["sequence_number"]) for m in detail["messages"]] == [
        ("user", 0),
        ("assistant", 1),
    ]
    assert detail["messages"][1]["content"] == "Because it streams."


async def test_the_done_event_carries_what_phase_5_will_record(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_stream(monkeypatch, parts=["ok"])
    chat = await _new_chat(client)
    await _ask(client, str(chat["id"]))

    done = dict(_parse_sse((await client.post(f"/chats/{chat['id']}/answer")).text)[-1][1])

    # Both the alias (the application's vocabulary) and the model that actually
    # served it: the mapping between them changes over time, so neither alone
    # identifies the run.
    assert done["alias"] == "learning-fast"
    assert done["provider_model"] == "stub-model"
    assert done["input_tokens"] == 7
    assert done["truncated"] is False


async def test_a_truncated_answer_is_flagged_not_hidden(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`length` means the model hit the ceiling mid-sentence.

    It is still persisted — the user watched it arrive — but the client is told,
    because from Phase 3 these transcripts become approved Learnings and a
    silently-truncated one is corrupted knowledge.
    """
    _stub_stream(monkeypatch, parts=["cut off here"], finish_reason="length")
    chat = await _new_chat(client)
    await _ask(client, str(chat["id"]))

    done = dict(_parse_sse((await client.post(f"/chats/{chat['id']}/answer")).text)[-1][1])
    assert done["truncated"] is True


async def test_a_gateway_failure_mid_stream_persists_nothing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure mode that matters most.

    Persistence hangs off the final chunk, which only arrives when the model
    finished. A stream that dies partway leaves the chat exactly as it was: a
    missing answer is recoverable by asking again, a half-answer recorded as
    complete is not.
    """
    from ai_core import GatewayError

    _stub_stream(monkeypatch, parts=["half an ans"], error=GatewayError("provider exploded"))
    chat = await _new_chat(client)
    await _ask(client, str(chat["id"]))

    events = _parse_sse((await client.post(f"/chats/{chat['id']}/answer")).text)
    names = [name for name, _ in events]
    assert names[-1] == "error"
    assert "done" not in names

    detail = (await client.get(f"/chats/{chat['id']}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user"]


async def test_an_empty_answer_is_reported_and_not_persisted(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_stream(monkeypatch, parts=["   "])
    chat = await _new_chat(client)
    await _ask(client, str(chat["id"]))

    events = _parse_sse((await client.post(f"/chats/{chat['id']}/answer")).text)
    assert events[-1][0] == "error"
    detail = (await client.get(f"/chats/{chat['id']}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user"]


async def test_refuses_to_answer_an_empty_chat(client: AsyncClient) -> None:
    chat = await _new_chat(client)
    response = await client.post(f"/chats/{chat['id']}/answer")
    assert response.status_code == 409
    assert "no messages" in response.json()["detail"]


async def test_refuses_to_answer_its_own_answer(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise the model replies to itself, and a stuck client can run up a
    bill one keystroke at a time."""
    _stub_stream(monkeypatch, parts=["an answer"])
    chat = await _new_chat(client)
    await _ask(client, str(chat["id"]))
    await client.post(f"/chats/{chat['id']}/answer")

    again = await client.post(f"/chats/{chat['id']}/answer")
    assert again.status_code == 409
    assert "not a question" in again.json()["detail"]


async def test_refuses_to_answer_a_deleted_chat(client: AsyncClient) -> None:
    chat = await _new_chat(client)
    await _ask(client, str(chat["id"]))
    await client.delete(f"/chats/{chat['id']}")

    response = await client.post(f"/chats/{chat['id']}/answer")
    assert response.status_code == 409


async def test_validation_errors_arrive_as_status_codes_not_sse_events(
    client: AsyncClient,
) -> None:
    """Once a stream is open the status line is already sent, so a 404 can no
    longer be expressed. Everything checkable is therefore checked before the
    response begins — this asserts that ordering."""
    response = await client.post("/chats/11111111-2222-3333-4444-555555555555/answer")
    assert response.status_code == 404
    assert not response.headers["content-type"].startswith("text/event-stream")


async def test_the_whole_transcript_is_sent_as_context(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 1's working-context strategy is "full history" (docs/SPEC.md §14).

    Asserted because it is a *choice*, not an accident: Phase 2 replaces it with
    a `build_context` node, and this test is what will notice.
    """
    from ai_core.graphs import chat as chat_graph_module

    seen: list[object] = []

    async def capture(request: Any) -> AsyncIterator[object]:
        seen.append(request)
        from ai_core import CompletionResponse, FinalChunk, ModelAlias

        yield FinalChunk(
            response=CompletionResponse(
                alias=ModelAlias.LEARNING_FAST,
                provider_model="stub",
                text="ok",
                input_tokens=1,
                output_tokens=1,
                finish_reason="stop",
            )
        )

    monkeypatch.setattr(chat_graph_module, "stream", capture)

    chat = await _new_chat(client)
    await _ask(client, str(chat["id"]), "first question")
    await client.post(f"/chats/{chat['id']}/answer")
    await _ask(client, str(chat["id"]), "second question")
    await client.post(f"/chats/{chat['id']}/answer")

    last_request = seen[-1]
    turns = last_request.messages  # type: ignore[attr-defined]

    # Phase 9: the transcript is preceded by the `learning_answer` system prompt.
    # Asserted as its own fact rather than folded into the list below, because it
    # is the thing that was *missing* for eight phases — the evaluation suite
    # found the gap, and this is what would notice if it disappeared again.
    assert turns[0].role == "system"
    assert "most recent question" in turns[0].content

    assert [turn.content for turn in turns[1:]] == [
        "first question",
        "ok",
        "second question",
    ]
    # The alias, not a model string — CLAUDE.md invariant #2 at the call site.
    assert last_request.alias.value == "learning-fast"  # type: ignore[attr-defined]


async def test_the_context_does_not_double_across_turns(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: threading the graph by chat id silently doubled the context.

    The database owns the transcript, so this handler seeds the graph with the
    full history on every request. When the checkpointer thread was keyed by chat
    id alone it already held the previous turns, and `add_messages` appended the
    freshly-rebuilt copies instead of recognising them — it matches on message
    id, and these are constructed from rows each time. Turn two sent
    ["q1", "a1", "q1", "a1", "q2"].

    Nothing errored. The bill just grew, and the model saw a conversation that
    stuttered. Hence a test that counts, rather than trusting the thread key to
    stay right.
    """
    from ai_core.graphs import chat as chat_graph_module

    seen: list[Any] = []

    async def capture(request: Any) -> AsyncIterator[object]:
        seen.append(request)
        from ai_core import CompletionResponse, FinalChunk, ModelAlias, TokenChunk

        yield TokenChunk(text="ok")
        yield FinalChunk(
            response=CompletionResponse(
                alias=ModelAlias.LEARNING_FAST,
                provider_model="stub",
                text="ok",
                input_tokens=1,
                output_tokens=1,
                finish_reason="stop",
            )
        )

    monkeypatch.setattr(chat_graph_module, "stream", capture)

    chat = await _new_chat(client)
    for question in ("q1", "q2", "q3"):
        await _ask(client, str(chat["id"]), question)
        await client.post(f"/chats/{chat['id']}/answer")

    # Turn N sees exactly the 2N-1 turns that precede it: no repeats, and each
    # request grows by exactly one question and one answer.
    # One system turn plus the transcript, so the counts are [1,3,5] + 1 each.
    # The *shape* is what this regression test is about — 2, 4, 6 grows by two
    # per turn; the doubling bug grew by four.
    assert [len(request.messages) for request in seen] == [2, 4, 6]
    # `[1:]` skips the `learning_answer` system prompt (Phase 9); this test is
    # about the transcript not doubling, not about the prompt.
    assert [turn.content for turn in seen[-1].messages[1:]] == ["q1", "ok", "q2", "ok", "q3"]


# --- safety ---------------------------------------------------------------------


async def test_a_blocked_question_ends_the_stream_with_blocked_not_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal is the system working, so it must not look like a failure.

    The client renders these differently — "we declined, here is why" against
    "something broke, try again" — and collapsing them would teach the user to
    retry a message that will always be refused.
    """
    _stub_stream(monkeypatch, parts=["should never be generated"])
    _stub_safety(monkeypatch, on_input=SafetyAction.BLOCK)
    chat_id = await _chat_with_question(client, "something forbidden")

    events = _parse_sse((await client.post(f"/chats/{chat_id}/answer")).text)
    names = [name for name, _ in events]
    assert "blocked" in names
    assert "done" not in names
    assert "error" not in names
    assert "token" not in names  # refused before the model was called

    payload = next(data for name, data in events if name == "blocked")
    assert payload["stage"] == "input"
    assert payload["persisted"] is False


async def test_a_blocked_answer_leaves_no_assistant_message(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tokens were shown; the transcript stays clean.

    This is the enforcement that matters downstream: a summary is built from
    messages, so an answer that never becomes a message can never become a
    Learning (CLAUDE.md invariant #5).
    """
    _stub_stream(monkeypatch, parts=["bad ", "answer"])
    _stub_safety(monkeypatch, on_output=SafetyAction.BLOCK)
    chat_id = await _chat_with_question(client, "a question")

    events = _parse_sse((await client.post(f"/chats/{chat_id}/answer")).text)
    assert [name for name, _ in events].count("token") == 2  # already streamed
    assert next(data for name, data in events if name == "blocked")["stage"] == "output"

    detail = (await client.get(f"/chats/{chat_id}")).json()
    assert [message["role"] for message in detail["messages"]] == ["user"]


async def test_an_allowed_interaction_still_records_its_checks(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, db: AsyncSession
) -> None:
    """ "Checked and fine" must be distinguishable from "never checked"."""
    _stub_stream(monkeypatch, parts=["an answer"])
    chat_id = await _chat_with_question(client, "a fine question")
    await client.post(f"/chats/{chat_id}/answer")

    rows = (
        (await db.execute(select(SafetyEvent).where(SafetyEvent.chat_id == uuid.UUID(chat_id))))
        .scalars()
        .all()
    )
    assert {row.stage for row in rows} == {"input", "output"}
    assert all(row.action == "allow" for row in rows)
    assert all(row.policy_version for row in rows)


async def test_an_output_event_is_linked_to_the_message_it_judged(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, db: AsyncSession
) -> None:
    """The check runs before the row exists, so the link is backfilled on persist.

    Without it an auditor asking "what was decided about this message" would have
    to reconstruct the answer from timestamps.
    """
    _stub_stream(monkeypatch, parts=["an answer"])
    chat_id = await _chat_with_question(client, "a question")
    body = (await client.post(f"/chats/{chat_id}/answer")).text
    message_id = next(data for name, data in _parse_sse(body) if name == "done")["message_id"]

    rows = (
        (await db.execute(select(SafetyEvent).where(SafetyEvent.chat_id == uuid.UUID(chat_id))))
        .scalars()
        .all()
    )
    by_stage = {row.stage: row for row in rows}
    assert str(by_stage["output"].message_id) == message_id
    # The input check judged the question, not the answer, and claiming otherwise
    # would make the audit trail say something false.
    assert by_stage["input"].message_id is None


async def test_a_blocked_interaction_is_still_recorded(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, db: AsyncSession
) -> None:
    """The case the table exists for: no message row, so the event is the only trace."""
    _stub_stream(monkeypatch, parts=["never mind"])
    _stub_safety(monkeypatch, on_input=SafetyAction.BLOCK)
    chat_id = await _chat_with_question(client, "something forbidden")
    await client.post(f"/chats/{chat_id}/answer")

    rows = (
        (await db.execute(select(SafetyEvent).where(SafetyEvent.chat_id == uuid.UUID(chat_id))))
        .scalars()
        .all()
    )
    assert [row.action for row in rows] == ["block"]
    assert rows[0].message_id is None


async def _chat_with_question(client: AsyncClient, question: str) -> str:
    chat_id = (await client.post("/chats", json={"title": "safety"})).json()["id"]
    await client.post(f"/chats/{chat_id}/messages", json={"role": "user", "content": question})
    return str(chat_id)


# --- model runs -----------------------------------------------------------------
#
# Scoped by `provider_model == "stub-model"`, never `select(ModelRun)` bare. The
# test database is the same Postgres the dev stack runs against, so a bare query
# picks up runs committed by real requests — which is how this file first
# "failed": a live `gpt-4o-mini` run from a browser session, priced and
# committed, was the row the unpriced-model assertion happened to read.


async def _stub_runs(db: AsyncSession) -> list[ModelRun]:
    """This suite's model runs, newest first.

    `expire_all` because `record_safety` marks a blocked run with a bulk UPDATE:
    the statement reaches the database, but the ORM object already in this
    session's identity map keeps its old attributes, and the harness deliberately
    uses `expire_on_commit=False`. A real request would read a fresh session and
    see the new value; only this shared-session test needs telling.
    """
    db.expire_all()
    result = await db.execute(
        select(ModelRun)
        .where(ModelRun.provider_model == "stub-model")
        .order_by(ModelRun.created_at.desc())
    )
    return list(result.scalars().all())


async def test_an_answer_records_what_it_cost(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, db: AsyncSession
) -> None:
    """docs/SPEC.md §17's `model_run`, written on the way past.

    The alias and the provider model are both recorded because both move
    independently — a row that knew only one could answer neither "what does this
    role cost" nor "which model got slower".
    """
    _stub_stream(monkeypatch, parts=["an answer"])
    chat_id = await _chat_with_question(client, "a question")
    await client.post(f"/chats/{chat_id}/answer")

    run = next(r for r in await _stub_runs(db) if r.operation == "chat.answer")
    assert run.model_alias == "learning-fast"
    assert run.provider_model == "stub-model"
    assert run.input_tokens == 7
    assert run.status == "ok"
    assert run.latency_ms >= 0


async def test_the_answer_message_points_at_its_run(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, db: AsyncSession
) -> None:
    """The link that makes "what did this answer cost" a single query."""
    _stub_stream(monkeypatch, parts=["an answer"])
    chat_id = await _chat_with_question(client, "a question")
    body = (await client.post(f"/chats/{chat_id}/answer")).text
    message_id = next(data for name, data in _parse_sse(body) if name == "done")["message_id"]

    message = (
        await db.execute(select(Message).where(Message.id == uuid.UUID(str(message_id))))
    ).scalar_one()
    assert message.model_run_id is not None
    run = (
        await db.execute(select(ModelRun).where(ModelRun.id == message.model_run_id))
    ).scalar_one()
    assert run.operation == "chat.answer"


async def test_a_blocked_answer_still_records_its_run(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, db: AsyncSession
) -> None:
    """The tokens were spent whether or not anyone got the answer.

    A run table that recorded only delivered answers would understate spend by
    exactly the amount spent on the refused ones — which is the number most worth
    watching, because nothing else in the product reveals it.
    """
    _stub_stream(monkeypatch, parts=["bad answer"])
    _stub_safety(monkeypatch, on_output=SafetyAction.BLOCK)
    chat_id = await _chat_with_question(client, "a question")
    await client.post(f"/chats/{chat_id}/answer")

    run = next(r for r in await _stub_runs(db) if r.operation == "chat.answer")
    # `blocked`, not `error`: the call itself worked, and an operator reading a
    # spike of one would draw the wrong conclusion from the other.
    assert run.status == "blocked"
    assert run.output_tokens > 0


async def test_an_unpriced_model_records_no_cost_rather_than_zero(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, db: AsyncSession
) -> None:
    """A zero would be a claim that the call was free, and it would sum.

    `stub-model` is deliberately absent from the price table, so this is the
    unknown-model path exactly as it would happen with a newly configured alias.
    """
    _stub_stream(monkeypatch, parts=["an answer"])
    chat_id = await _chat_with_question(client, "a question")
    await client.post(f"/chats/{chat_id}/answer")

    run = next(r for r in await _stub_runs(db) if r.operation == "chat.answer")
    assert run.estimated_cost is None
