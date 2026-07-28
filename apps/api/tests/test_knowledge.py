"""Behavioural contract for the summary-draft and Learning endpoints.

Against a real Postgres, with the model stubbed. The endpoints' job is the
approval gate — what may be promoted, by whom, and what is recorded — and none of
that depends on the quality of a generated summary.

Most of these assert that something does **not** happen. That is the shape of a
gate: the interesting cases are the ones it refuses.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_core.agents.summariser import GeneratedSummary
from ai_core.graphs import summary as summary_module
from ai_core.graphs.chat import build_chat_graph
from ai_core.graphs.summary import build_summary_graph
from ai_core.models.aliases import ModelAlias
from ai_core.schemas.summary import LearningSummary
from api.main import app
from api.routers import knowledge as knowledge_module
from database.session import engine, session

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _summary(**overrides: Any) -> LearningSummary:
    body: dict[str, Any] = {
        "title": "Indexes and primary keys",
        "overview": (
            "A primary key uniquely identifies a row and implies a unique index, "
            "whereas an index is a separate structure that speeds lookups."
        ),
        "key_concepts": ["A primary key implies a unique index"],
        "uncertainty_notes": ["NULL handling probably varies by engine"],
    }
    body.update(overrides)
    return LearningSummary.model_validate(body)


@pytest.fixture
async def client(anyio_backend: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    try:
        connection = await engine().connect()
    except DBAPIError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no database reachable ({type(exc).__name__}) — run `make up`")

    transaction = await connection.begin()
    test_session = AsyncSession(bind=connection, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield test_session

    async def fake_summarise(_: str) -> GeneratedSummary:
        return GeneratedSummary(
            summary=_summary(), prompt_version="learning_summary@1", alias=ModelAlias.LEARNING_DEEP
        )

    monkeypatch.setattr(summary_module, "summarise", fake_summarise)

    # Approving and editing re-index the Learning (Phase 8), which is an embedding
    # call. Unstubbed, these tests reach for the gateway at its in-network
    # hostname, which does not resolve from the host — and because
    # `_reindex_quietly` swallows the failure, they still *passed*, just ten
    # seconds slower each. The suite went from 5s to 75s and stayed green, which
    # is the worst way for a test to tell you something is wrong.
    async def fake_index(db: object, learning: object) -> int:
        return 0

    monkeypatch.setattr(knowledge_module, "index_learning", fake_index)

    app.dependency_overrides[session] = override_session
    # Both graphs, sharing an in-memory checkpointer — the summary graph needs one
    # at all, since its approval interrupt has nowhere to keep state without it.
    saver = InMemorySaver()
    app.state.chat_graph = build_chat_graph().compile(checkpointer=saver)
    app.state.summary_graph = build_summary_graph().compile(checkpointer=saver)
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


async def _chat_with_history(client: AsyncClient) -> str:
    chat = (await client.post("/chats", json={"title": "A chat"})).json()
    await client.post(f"/chats/{chat['id']}/messages", json={"content": "What is an index?"})
    return str(chat["id"])


async def _learnings_from(client: AsyncClient, chat_id: str) -> list[dict[str, Any]]:
    """Learnings derived from one chat.

    Scoped rather than "all learnings": the fixture rolls back its own writes, but
    a developer's database legitimately holds real Learnings from actually using
    the app. A test that asserts the library is globally empty passes only on a
    pristine database and fails for reasons that have nothing to do with the code.
    """
    listed = (await client.get("/learnings?include_deleted=true")).json()
    return [row for row in listed if row["source_chat_id"] == chat_id]


async def _draft(client: AsyncClient) -> dict[str, Any]:
    chat_id = await _chat_with_history(client)
    response = await client.post(f"/chats/{chat_id}/summary")
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


# --- generating ----------------------------------------------------------------


async def test_generating_produces_a_draft_and_not_a_learning(client: AsyncClient) -> None:
    """The whole point of the phase, in one assertion.

    A generated summary is model output awaiting review. If this ever creates a
    `learning`, CLAUDE.md invariant #5 is broken.
    """
    draft = await _draft(client)

    assert draft["status"] == "pending"
    # docs/SPEC.md §12: the record says which prompt version produced it.
    assert draft["prompt_version"] == "learning_summary@1"
    assert await _learnings_from(client, draft["chat_id"]) == []


async def test_regenerating_supersedes_the_previous_draft(client: AsyncClient) -> None:
    """At most one draft may await review, or "approve the draft" is ambiguous.

    The old one is marked rejected rather than deleted — "the model proposed this
    and I asked for another" is a signal Phase 6 evaluates on.
    """
    chat_id = await _chat_with_history(client)
    first = (await client.post(f"/chats/{chat_id}/summary")).json()
    second = (await client.post(f"/chats/{chat_id}/summary")).json()

    assert first["id"] != second["id"]
    pending = (await client.get(f"/chats/{chat_id}/summary")).json()
    assert pending["id"] == second["id"]


async def test_summarising_an_empty_chat_is_refused(client: AsyncClient) -> None:
    chat = (await client.post("/chats", json={"title": "empty"})).json()
    response = await client.post(f"/chats/{chat['id']}/summary")
    assert response.status_code == 409


# --- editing a draft -----------------------------------------------------------


async def test_a_draft_can_be_edited_before_approval(client: AsyncClient) -> None:
    draft = await _draft(client)
    body = dict(draft["structured_content"])
    body["title"] = "My own title"

    response = await client.patch(f"/summaries/{draft['id']}", json=body)
    assert response.status_code == 200
    assert response.json()["title"] == "My own title"
    # Still a draft: editing is not deciding.
    assert response.json()["status"] == "pending"
    assert await _learnings_from(client, draft["chat_id"]) == []


# --- approving -----------------------------------------------------------------


async def test_approving_creates_the_learning_and_its_first_revision(
    client: AsyncClient,
) -> None:
    draft = await _draft(client)
    response = await client.post(f"/summaries/{draft['id']}/approve")

    assert response.status_code == 201
    learning = response.json()
    assert learning["approved_at"] is not None
    # Revision 1 is `model`: the text originated as a generated draft, whatever
    # the user did to it before approving. That distinction is the column's
    # entire purpose.
    assert [(r["revision_number"], r["change_source"]) for r in learning["revisions"]] == [
        (1, "model")
    ]


async def test_approving_promotes_the_edited_content_not_the_original(
    client: AsyncClient,
) -> None:
    """The user approves what they are looking at.

    Promoting the model's original text would mean the approval applied to
    something the user never saw — which is the failure the review step exists to
    prevent.
    """
    draft = await _draft(client)
    body = dict(draft["structured_content"])
    body["title"] = "Corrected by me"
    await client.patch(f"/summaries/{draft['id']}", json=body)

    learning = (await client.post(f"/summaries/{draft['id']}/approve")).json()
    assert learning["title"] == "Corrected by me"


async def test_a_draft_cannot_be_approved_twice(client: AsyncClient) -> None:
    """Otherwise one draft yields two Learnings and the library has a duplicate
    whose origin the user cannot distinguish."""
    draft = await _draft(client)
    assert (await client.post(f"/summaries/{draft['id']}/approve")).status_code == 201

    again = await client.post(f"/summaries/{draft['id']}/approve")
    assert again.status_code == 409
    assert len(await _learnings_from(client, draft["chat_id"])) == 1


async def test_a_rejected_draft_cannot_be_approved(client: AsyncClient) -> None:
    draft = await _draft(client)
    assert (await client.post(f"/summaries/{draft['id']}/reject")).status_code == 204

    assert (await client.post(f"/summaries/{draft['id']}/approve")).status_code == 409
    assert await _learnings_from(client, draft["chat_id"]) == []


async def test_rejecting_promotes_nothing(client: AsyncClient) -> None:
    draft = await _draft(client)
    await client.post(f"/summaries/{draft['id']}/reject")

    assert await _learnings_from(client, draft["chat_id"]) == []
    # No longer pending, so it will not be offered for review again.
    assert (await client.get(f"/chats/{draft['chat_id']}/summary")).status_code == 404


# --- the library ---------------------------------------------------------------


async def test_editing_a_learning_appends_a_human_revision(client: AsyncClient) -> None:
    """History, not overwrite.

    Regression guard as well as a contract: an earlier version returned the
    *stale* revision list here, because the session's identity map held the
    collection loaded before the insert. The write was correct and the response
    lied.
    """
    draft = await _draft(client)
    learning = (await client.post(f"/summaries/{draft['id']}/approve")).json()

    body = dict(learning["structured_content"])
    body["overview"] = body["overview"] + " I added this."
    response = await client.patch(
        f"/learnings/{learning['id']}", json={"content": body, "note": "clarified"}
    )

    assert response.status_code == 200
    assert [(r["revision_number"], r["change_source"]) for r in response.json()["revisions"]] == [
        (1, "model"),
        (2, "human"),
    ]


async def test_a_learning_survives_deleting_its_source_chat(client: AsyncClient) -> None:
    """`source_chat_id` is ON DELETE SET NULL, not CASCADE.

    Deleting a conversation must not delete the knowledge derived from it — that
    a Learning outlives its chat is the reason approving one is worth doing.
    """
    draft = await _draft(client)
    learning = (await client.post(f"/summaries/{draft['id']}/approve")).json()

    await client.delete(f"/chats/{draft['chat_id']}")

    still_there = await client.get(f"/learnings/{learning['id']}")
    assert still_there.status_code == 200


async def test_learnings_are_soft_deleted_and_restorable(client: AsyncClient) -> None:
    draft = await _draft(client)
    learning = (await client.post(f"/summaries/{draft['id']}/approve")).json()

    assert (await client.delete(f"/learnings/{learning['id']}")).status_code == 204
    live = (await client.get("/learnings")).json()
    assert not any(row["id"] == learning["id"] for row in live)
    assert len(await _learnings_from(client, draft["chat_id"])) == 1

    restored = await client.post(f"/learnings/{learning['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None


async def test_there_is_no_endpoint_that_creates_a_learning_directly(
    client: AsyncClient,
) -> None:
    """Invariant #5 in the URL space.

    Approval is the only route into the library. A `POST /learnings` would be a
    way to add knowledge without a draft ever being reviewed — so its absence is
    asserted rather than assumed.
    """
    assert (await client.post("/learnings", json={"title": "x"})).status_code == 405
