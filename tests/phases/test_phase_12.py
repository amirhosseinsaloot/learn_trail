"""Phase 12 — Advanced learning features

See docs/SPEC.md, "Phase 12 — Advanced learning features" section, for the full
Build/AI-stack/Learn breakdown. This file only encodes the exit criterion as an
executable check.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

pytestmark = [pytest.mark.phase, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.phase
async def test_phase_12_exit_criterion() -> None:
    """Phase 12 — Advanced learning features.

    docs/SPEC.md states no verbatim exit criterion; the plan's proxy is used
    (plans/phase-12.md):

        "At least one advanced learning feature (quiz generation, flashcards,
        spaced repetition, knowledge graph, learning-path recommendations,
        document ingestion, voice interface, MCP-based tools, or Markdown/PDF
        export) is implemented and covered by its own passing test."

    The feature built is **flashcard generation from an approved Learning**. It is
    the one that exercises the whole platform one more time — alias-based typed
    generation, Pydantic validation (invariant #4), an endpoint, a UI — which is a
    fitting thing for the last phase to demonstrate.

    Four claims.

    **The output is validated, not merely parsed.** A degenerate set — a card
    whose answer restates its question, or a set of one — is rejected by the
    schema before it can reach a response.

    **The endpoint generates from an approved Learning.** With the model stubbed,
    `POST /learnings/{id}/flashcards` returns a set carrying the Learning's id.

    **It refuses what is not approved knowledge.** A deleted Learning is a 409, a
    missing one a 404 — flashcards come from the library, not from anything.

    **The model is stubbed.** Like every phase test, this runs under `make status`
    without spending money; live generation is verified by hand and by the
    endpoint's own suite.
    """
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import AsyncSession

    from ai_core.schemas.flashcards import Flashcard, FlashcardSet
    from api.main import app
    from api.routers import knowledge as knowledge_module
    from database.models import Learning
    from database.session import engine, session

    # --- the output is validated -----------------------------------------------
    # A card that restates itself, and a set that is too small, are both
    # well-formed JSON and useless — the schema is what tells them apart.
    with pytest.raises(ValueError, match="front and back must differ"):
        Flashcard.model_validate({"front": "A B-tree", "back": "a b-tree"})
    with pytest.raises(ValueError):
        FlashcardSet.model_validate({"cards": [{"front": "q?", "back": "a"}]})

    # --- the endpoint, against a real DB with the model stubbed ----------------
    try:
        connection = await engine().connect()
    except DBAPIError:  # pragma: no cover - depends on the environment
        pytest.skip("no database reachable — run `make up`")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db

    async def fake_generate(learning: str) -> FlashcardSet:
        # No model call. The point under test is the endpoint's contract, not the
        # model's output — that is what the schema and the live check cover.
        return FlashcardSet(
            cards=[
                Flashcard(front="What is an index?", back="a structure that speeds lookups"),
                Flashcard(front="What does a primary key do?", back="uniquely identifies a row"),
                Flashcard(front="Why use a foreign key?", back="to reference another table"),
            ]
        )

    # Patched through an `Any`-typed alias: the function is imported into the
    # knowledge module, not re-exported, so mypy will not see it as an
    # assignable attribute otherwise. Restored via the rolled-back module state
    # is unnecessary — the process ends with the test.
    module: Any = knowledge_module
    module.generate_flashcards = fake_generate
    app.dependency_overrides[session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://learntrail.test"
        ) as http:
            # An approved Learning, written straight to the rolled-back transaction.
            approved = Learning(
                title="Indexes",
                structured_content={
                    "title": "Indexes",
                    "overview": "An index speeds up lookups.",
                    "key_concepts": ["a primary key implies a unique index"],
                },
            )
            db.add(approved)
            await db.flush()
            approved_id = str(approved.id)

            # Generates from the approved Learning.
            ok = await http.post(f"/learnings/{approved_id}/flashcards")
            assert ok.status_code == 201, ok.text
            body = ok.json()
            assert body["learning_id"] == approved_id, (
                "the set does not name the Learning it came from, so a reviewer "
                "cannot check the cards against their source"
            )
            assert len(body["cards"]) >= 3
            assert all(card["front"] != card["back"] for card in body["cards"])

            # A missing Learning is a 404.
            missing = await http.post("/learnings/11111111-2222-3333-4444-555555555555/flashcards")
            assert missing.status_code == 404

            # A deleted Learning is a 409 — you do not study from what you removed.
            deleted = Learning(
                title="Removed", structured_content={"title": "Removed", "overview": "gone"}
            )
            from sqlalchemy import func

            deleted.deleted_at = func.now()
            db.add(deleted)
            await db.flush()
            refused = await http.post(f"/learnings/{deleted.id}/flashcards")
            assert refused.status_code == 409, (
                "flashcards were generated from a deleted Learning; a removed "
                "Learning must not be a source"
            )
    finally:
        app.dependency_overrides.clear()
        await db.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
