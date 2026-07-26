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

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.main import app
from database.session import engine, session

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(anyio_backend: str) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired to the app, sharing one rolled-back transaction."""
    try:
        connection = await engine().connect()
    except DBAPIError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no database reachable ({type(exc).__name__}) — run `make up`")

    transaction = await connection.begin()
    test_session = AsyncSession(bind=connection, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield test_session

    # The override is what keeps the handlers on this transaction. Without it
    # they would open their own sessions against the engine, commit for real, and
    # leave rows behind.
    app.dependency_overrides[session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://learntrail.test"
        ) as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        await test_session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


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
