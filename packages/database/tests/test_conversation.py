"""Behavioural contract for `chat` and `message`, against a real Postgres.

Why a real database rather than mocks: every assertion here is about something
only Postgres enforces — CHECK constraints, a unique constraint, `ON DELETE
CASCADE`, and the VARCHAR-plus-CHECK enum round-tripping back into a Python
enum. A mocked session would assert that SQLAlchemy builds the statement, which
is not the property that matters.

These tests **skip** (never fail) when no database is reachable, so `make test`
stays runnable on a machine with the stack down. Run `make up` to exercise them.

Nothing here commits. Each test runs inside a transaction that the fixture rolls
back, so the tests neither see nor leave any state — which is also why they use
`flush()`: it sends the INSERT and trips the constraint without persisting.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Chat, ChatStatus, Message, MessageRole
from database.session import engine, session_factory


@pytest.fixture
def anyio_backend() -> str:
    """Run the async tests on asyncio only (no trio in this project)."""
    return "asyncio"


@pytest.fixture
async def db(anyio_backend: str) -> AsyncIterator[AsyncSession]:
    """An open session whose transaction is always rolled back.

    The connectivity probe is the `begin()` itself: if Postgres is not up, the
    connection attempt raises here and the test is skipped with an actionable
    message instead of failing.
    """
    try:
        connection = await engine().connect()
    except DBAPIError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no database reachable ({type(exc).__name__}) — run `make up`")

    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        # A failed flush aborts the transaction itself, so by the time a
        # constraint test finishes there may be nothing left to roll back.
        # Rolling back unconditionally works but emits a spurious SAWarning
        # ("transaction already deassociated from connection") on every such
        # test, which trains the reader to ignore warnings.
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


def _chat(**overrides: object) -> Chat:
    """A valid chat, so each test states only the field it is about."""
    return Chat(**{"title": "A chat", **overrides})


pytestmark = pytest.mark.anyio


async def test_a_new_chat_is_active_and_undeleted(db: AsyncSession) -> None:
    chat = _chat()
    db.add(chat)
    await db.flush()

    # `status` defaults rather than being passed in: a chat is created active,
    # and the caller should not have to say so.
    assert chat.status is ChatStatus.ACTIVE
    assert chat.deleted_at is None
    # server_default=now(), so this is populated by the INSERT, not by Python.
    assert chat.created_at is not None


async def test_enum_columns_load_back_as_enums_not_strings(db: AsyncSession) -> None:
    """The `Mapped[...]` annotations must be true on the read path too.

    A bare `String` column would return `str` here. It compares equal to the
    StrEnum member, so equality assertions pass either way — which is exactly why
    this test checks `isinstance` instead. Without it, a regression to `String`
    would be invisible until some enum-only attribute access crashed at runtime.
    """
    chat = _chat()
    chat.messages.append(Message(role=MessageRole.ASSISTANT, content="hi", sequence_number=0))
    db.add(chat)
    await db.flush()

    # Drop the identity map so the next read genuinely comes from Postgres
    # rather than from the objects constructed above.
    db.expunge_all()

    loaded = (await db.execute(select(Chat).where(Chat.id == chat.id))).scalar_one()
    assert isinstance(loaded.status, ChatStatus)
    assert isinstance(loaded.messages[0].role, MessageRole)


def test_the_role_enum_itself_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="not a valid MessageRole"):
        MessageRole("moderator")


async def test_rejects_an_unknown_role_string_at_the_bind_layer(db: AsyncSession) -> None:
    """`validate_strings=True` catches a raw string that bypassed the enum.

    Type annotations do not survive `setattr` from untyped data (a dict from a
    request body, say), so the column type is the last line of defence before a
    junk role reaches Postgres. Without `validate_strings` SQLAlchemy passes the
    string straight through and only the CHECK constraint objects — a database
    round-trip later, with a much worse error.
    """
    chat = _chat()
    message = Message(role=MessageRole.USER, content="q", sequence_number=0)
    chat.messages.append(message)
    db.add(chat)
    await db.flush()

    message.role = "moderator"  # type: ignore[assignment]  # smuggled past the enum
    with pytest.raises(StatementError):
        await db.flush()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        # A blank title renders as an invisible row in the chat list. NULL is
        # allowed (untitled); whitespace is not.
        ("title", ""),
        ("title", "   "),
    ],
)
async def test_rejects_a_blank_chat_title(db: AsyncSession, field: str, value: str) -> None:
    db.add(_chat(**{field: value}))
    with pytest.raises(IntegrityError, match="title_not_blank"):
        await db.flush()


async def test_allows_an_untitled_chat(db: AsyncSession) -> None:
    # A chat exists before it has been titled — the title is generated from the
    # conversation afterwards (docs/SPEC.md §6).
    chat = _chat(title=None)
    db.add(chat)
    await db.flush()
    assert chat.title is None


async def test_status_and_deleted_at_cannot_disagree(db: AsyncSession) -> None:
    """The redundancy between the two columns is enforced, not merely intended."""
    # Deleted status without a timestamp.
    db.add(_chat(status=ChatStatus.DELETED))
    with pytest.raises(IntegrityError, match="status_matches_deleted_at"):
        await db.flush()


async def test_soft_delete_sets_both_columns_together(db: AsyncSession) -> None:
    from datetime import UTC, datetime

    chat = _chat()
    db.add(chat)
    await db.flush()

    chat.status = ChatStatus.DELETED
    chat.deleted_at = datetime.now(UTC)
    await db.flush()

    # The row survives its own deletion — restoring it is just clearing these
    # two columns (docs/SPEC.md §6, "Deleting and restoring content").
    assert chat.id is not None


async def test_rejects_empty_message_content(db: AsyncSession) -> None:
    chat = _chat()
    chat.messages.append(Message(role=MessageRole.USER, content="", sequence_number=0))
    db.add(chat)
    with pytest.raises(IntegrityError, match="content_not_empty"):
        await db.flush()


async def test_rejects_a_negative_sequence_number(db: AsyncSession) -> None:
    chat = _chat()
    chat.messages.append(Message(role=MessageRole.USER, content="q", sequence_number=-1))
    db.add(chat)
    with pytest.raises(IntegrityError, match="sequence_number_non_negative"):
        await db.flush()


async def test_sequence_numbers_are_unique_within_a_chat(db: AsyncSession) -> None:
    """Two messages at the same position would make the transcript order ambiguous."""
    chat = _chat()
    chat.messages.append(Message(role=MessageRole.USER, content="first", sequence_number=0))
    chat.messages.append(Message(role=MessageRole.ASSISTANT, content="second", sequence_number=0))
    db.add(chat)
    with pytest.raises(IntegrityError, match="uq_message_chat_id_sequence_number"):
        await db.flush()


async def test_the_same_sequence_number_is_fine_in_a_different_chat(db: AsyncSession) -> None:
    for title in ("first chat", "second chat"):
        chat = _chat(title=title)
        chat.messages.append(Message(role=MessageRole.USER, content="q", sequence_number=0))
        db.add(chat)
    await db.flush()  # must not raise: the constraint is per-chat, not global


async def test_messages_are_returned_in_sequence_order(db: AsyncSession) -> None:
    chat = _chat()
    # Appended out of order on purpose: ordering must come from the relationship's
    # `order_by`, not from insertion luck.
    for sequence_number in (2, 0, 1):
        chat.messages.append(
            Message(
                role=MessageRole.USER,
                content=f"message {sequence_number}",
                sequence_number=sequence_number,
            )
        )
    db.add(chat)
    await db.flush()
    db.expunge_all()

    loaded = (await db.execute(select(Chat).where(Chat.id == chat.id))).scalar_one()
    assert [m.sequence_number for m in loaded.messages] == [0, 1, 2]


async def test_deleting_a_chat_cascades_to_its_messages(db: AsyncSession) -> None:
    """Hard deletion is rare, but a message must never outlive its chat."""
    chat = _chat()
    chat.messages.append(Message(role=MessageRole.USER, content="q", sequence_number=0))
    db.add(chat)
    await db.flush()
    chat_id = chat.id

    await db.delete(chat)
    await db.flush()

    remaining = (
        (await db.execute(select(Message).where(Message.chat_id == chat_id))).scalars().all()
    )
    assert remaining == []


async def test_a_message_needs_a_chat(db: AsyncSession) -> None:
    db.add(Message(chat_id=uuid.uuid4(), role=MessageRole.USER, content="q", sequence_number=0))
    with pytest.raises(IntegrityError, match="fk_message_chat_id_chat"):
        await db.flush()


async def test_session_factory_keeps_objects_usable_after_commit() -> None:
    """`expire_on_commit=False` is load-bearing, not a style preference.

    With the default, reading any attribute after `commit()` triggers a refresh —
    an implicit await inside response construction, which raises MissingGreenlet
    on an async session. Asserting it here means a "tidy-up" that drops the flag
    fails a test instead of breaking requests.
    """
    assert session_factory().kw["expire_on_commit"] is False


def test_engine_is_cached_so_one_pool_is_shared() -> None:
    # A fresh pool per call would leak connections on every request.
    assert engine() is engine()


def test_no_statement_error_alias_drift() -> None:
    # IntegrityError must remain a StatementError subclass for the `match=`
    # assertions above to be meaningful; SQLAlchemy guarantees it, and this
    # documents the dependency.
    assert issubclass(IntegrityError, StatementError)
