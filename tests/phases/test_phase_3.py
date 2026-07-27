"""Phase 3 — Structured summary generation

See docs/SPEC.md, "Phase 3 — Structured summary generation" section, for the full
Build/AI-stack/Learn breakdown. This file only encodes the exit criterion as an
executable check.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytestmark = pytest.mark.phase


@pytest.mark.phase
def test_phase_3_exit_criterion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 3 — Structured summary generation.

    Exit criterion (verbatim, docs/SPEC.md):

        "Malformed or incomplete summaries are rejected before persistence."

    Two words carry the weight, and each is asserted separately.

    **Rejected** — the schema refuses every shape a model can plausibly get
    wrong: a missing required field, an unknown field, a blank entry, a runaway
    list. These are checked directly against `LearningSummary`, which is the
    thing that does the rejecting.

    **Before persistence** — this is the structural half, and the one a schema
    test alone cannot show. The summary workflow orders its nodes so that
    `validate_summary` runs *before* `store_draft` and raises rather than
    returning, which makes persistence unreachable for a summary that fails. The
    test asserts that ordering against the graph's own declared sequence, and
    then proves it by running the graph with a deliberately invalid summary and
    checking that the storage callable was never invoked.

    **No model call.** Every rejection path is exercised with constructed values,
    so this runs on every `make status` without spending anything — the same
    contract as the Phase 1 test. Live generation is covered by the endpoint
    verification and by `packages/ai_core`'s tests.
    """
    from pydantic import ValidationError

    from ai_core.graphs.summary import NODE_SEQUENCE
    from ai_core.schemas.summary import MAX_ITEMS, LearningSummary

    # --- rejected: malformed ---------------------------------------------------
    valid: dict[str, Any] = {
        "title": "Indexes and primary keys",
        "overview": (
            "A primary key uniquely identifies a row and implies a unique index, "
            "whereas an index is a separate structure that speeds lookups."
        ),
        "key_concepts": ["A primary key implies a unique index"],
    }
    # Sanity: the fixture itself must be acceptable, or every rejection below
    # would pass for the wrong reason.
    LearningSummary.model_validate(valid)

    malformed: dict[str, dict[str, Any]] = {
        "unknown field": {**valid, "invented": "anything"},
        "blank list entry": {**valid, "key_concepts": ["   "]},
        "blank title": {**valid, "title": "  "},
        "runaway list": {**valid, "key_concepts": ["x"] * (MAX_ITEMS + 1)},
        "wrong type": {**valid, "key_concepts": "not a list"},
        "one-word overview": {**valid, "overview": "Databases."},
    }
    for description, body in malformed.items():
        with pytest.raises(ValidationError):
            LearningSummary.model_validate(body)
            pytest.fail(f"a {description} summary was accepted")

    # --- rejected: incomplete --------------------------------------------------
    for required in ("title", "overview", "key_concepts"):
        incomplete = {key: value for key, value in valid.items() if key != required}
        with pytest.raises(ValidationError):
            LearningSummary.model_validate(incomplete)
            pytest.fail(f"a summary missing {required} was accepted")

    # A summary that learned nothing is incomplete even though every key is
    # present — the criterion is about substance, not just key coverage.
    with pytest.raises(ValidationError):
        LearningSummary.model_validate({**valid, "key_concepts": []})

    # --- before persistence: the node order ------------------------------------
    assert NODE_SEQUENCE.index("validate_summary") < NODE_SEQUENCE.index("store_draft"), (
        f"validation must precede persistence, or the criterion is unenforceable: {NODE_SEQUENCE}"
    )

    # --- before persistence: demonstrated --------------------------------------
    stored = _run_with_invalid_summary(monkeypatch)
    assert stored == [], (
        "the graph persisted a summary that failed validation; "
        "`store_draft` must be unreachable when `validate_summary` raises"
    )


def _run_with_invalid_summary(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Run the summary graph on a summary that fails layer-4 validation.

    Returns whatever reached the storage callable — which must be nothing.

    The model is stubbed rather than called: the point is what the *graph* does
    with a summary it should refuse, and relying on a live model to produce one
    on demand would make this test both slow and flaky.
    """
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.memory import InMemorySaver

    from ai_core.agents.summariser import GeneratedSummary
    from ai_core.graphs import summary as summary_module
    from ai_core.graphs.summary import (
        APPLY_DECISION_KEY,
        LOAD_TRANSCRIPT_KEY,
        STORE_DRAFT_KEY,
        SummaryRejected,
        SummaryState,
        build_summary_graph,
    )
    from ai_core.models.aliases import ModelAlias
    from ai_core.schemas.summary import LearningSummary

    # A conversation that hedges repeatedly, paired with a summary that states
    # everything flatly. That is the layer-4 failure docs/SPEC.md §8 names:
    # uncertainty was not preserved.
    transcript = [
        ("user", "Is a unique index the same as a primary key?"),
        (
            "assistant",
            "Probably not identical — it depends on the engine, and I'm not certain "
            "the NULL behaviour is the same everywhere. It usually varies.",
        ),
    ]
    overconfident = LearningSummary.model_validate(
        {
            "title": "Unique indexes and primary keys",
            "overview": (
                "A unique index is exactly equivalent to a primary key in every "
                "database engine, with identical NULL handling in all cases."
            ),
            "key_concepts": ["A unique index is identical to a primary key"],
        }
    )

    stored: list[Any] = []

    async def load(_: str) -> list[tuple[str, str]]:
        return transcript

    async def fake_summarise(_: str) -> GeneratedSummary:
        return GeneratedSummary(
            summary=overconfident,
            prompt_version="learning_summary@1",
            alias=ModelAlias.LEARNING_DEEP,
        )

    async def store(generated: GeneratedSummary) -> str:
        stored.append(generated)
        return "should-never-happen"

    async def apply(draft_id: str, decision: Any) -> str:  # pragma: no cover - unreachable
        return "should-never-happen"

    # `monkeypatch` rather than manual save/restore: it undoes the patch even if
    # an assertion fails, so a failure here cannot leak a stubbed model into the
    # next test in the session.
    monkeypatch.setattr(summary_module, "summarise", fake_summarise)

    async def run() -> None:
        graph = build_summary_graph().compile(checkpointer=InMemorySaver())
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "phase-3-exit-criterion",
                LOAD_TRANSCRIPT_KEY: load,
                STORE_DRAFT_KEY: store,
                APPLY_DECISION_KEY: apply,
            }
        }
        with pytest.raises(SummaryRejected):
            await graph.ainvoke(SummaryState(chat_id="c1"), config=config)

    asyncio.run(run())
    return stored
