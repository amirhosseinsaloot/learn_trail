"""Postgres-backed checkpointing for graph state (docs/SPEC.md §15, Phase 2).

A checkpointer writes the graph's state after every node. Two things follow, and
only the second is about durability:

1. A run is *inspectable*. `graph.aget_state_history(config)` replays which nodes
   executed and what the state was after each — which is how "each chat request
   is visible as a deterministic graph execution" stops being a claim.
2. A run is *resumable*. Phase 3's summary graph interrupts for human approval
   (docs/SPEC.md §7), and an interrupt that cannot be resumed after a restart is
   not a human-in-the-loop workflow, it is a lost draft.

**One thread per request, not per conversation.** The obvious choice — thread id
= chat id — is wrong here and fails silently. The database owns the transcript,
so the API seeds the graph with the full history on every request; a thread that
already held the previous turns would *append* those fresh copies rather than
recognise them (`add_messages` matches on message id, and these are rebuilt from
rows each time). The context would double every turn, inflating cost and
confusing the model, with nothing in the logs to say so. Threads are therefore
`{chat_id}:{sequence_number}` — which also makes each request its own
inspectable execution, matching the Phase 2 criterion's wording.

**These tables are not ours.** LangGraph owns their schema and creates them via
`setup()`; they are deliberately outside Alembic, because a library migrating its
own storage on a schedule we do not control is not something to mirror in our
revisions. `alembic check` stays clean because our metadata never mentions them.
"""

from __future__ import annotations

import os
from contextlib import AbstractAsyncContextManager
from typing import Final

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

#: Our own types that end up inside a checkpoint, declared explicitly.
#:
#: LangGraph deserializes unregistered types with a warning today and will
#: **block them outright in a future version** — at which point every existing
#: checkpoint containing one becomes unreadable, and the failure arrives on a
#: dependency bump rather than on a change of ours. Registering them now costs
#: three lines and removes that entirely.
#:
#: A type reaching a checkpoint is a deliberate act: it means graph state carries
#: it between nodes. Anything added to `ChatState` in a later phase belongs here
#: too, and the warning in the logs is what says so.
ALLOWED_CHECKPOINT_TYPES: Final = [
    ("ai_core.graphs.chat", "ChatState"),
    ("ai_core.graphs.summary", "ReviewDecision"),
    ("ai_core.graphs.summary", "SummaryState"),
    ("ai_core.models.aliases", "ModelAlias"),
    ("ai_core.safety.decisions", "SafetyAction"),
    ("ai_core.safety.decisions", "SafetyDecision"),
    ("ai_core.safety.decisions", "SafetyOutcome"),
    ("ai_core.safety.decisions", "SafetyStage"),
    ("ai_core.schemas.completion", "CompletionResponse"),
    ("ai_core.schemas.summary", "LearningSummary"),
]

#: The checkpointer speaks to psycopg directly, not through SQLAlchemy, so it
#: needs a plain libpq URL — SQLAlchemy's `postgresql+psycopg://` dialect prefix
#: is meaningless to it and fails to parse. Deriving one from the other rather
#: than adding a second environment variable keeps a single source of truth for
#: where the database is.
_SQLALCHEMY_PREFIX: Final = "postgresql+psycopg://"
_LIBPQ_PREFIX: Final = "postgresql://"


def checkpointer_url(database_url: str) -> str:
    """Convert a SQLAlchemy URL into the libpq form the checkpointer expects."""
    if database_url.startswith(_SQLALCHEMY_PREFIX):
        return _LIBPQ_PREFIX + database_url[len(_SQLALCHEMY_PREFIX) :]
    return database_url


def checkpointer_url_from_env() -> str:
    """The checkpointer's connection string, from the same `DATABASE_URL`
    everything else uses.

    The default matches the compose service, exactly as
    `database.config.database_url` does — this module deliberately does not
    import that one, because `ai_core` depending on `database` for a *string*
    would be a coupling bought at a poor price.
    """
    return checkpointer_url(
        os.environ.get("DATABASE_URL")
        or "postgresql+psycopg://learntrail:learntrail@localhost:5432/learntrail"
    )


def open_checkpointer(url: str | None = None) -> AbstractAsyncContextManager[AsyncPostgresSaver]:
    """Open a checkpointer as an async context manager.

    Deliberately not cached and not a module-level singleton: the underlying
    connection pool is bound to an event loop, and a cached one leaks across
    loops in exactly the way that produces "attached to a different loop" errors
    hours later. The caller owns the lifetime — in the API that is the
    application lifespan.

    `setup()` must be awaited once on a fresh database to create LangGraph's
    tables; the API's lifespan does that at startup, where it is idempotent and
    cheap.
    """
    return AsyncPostgresSaver.from_conn_string(
        url or checkpointer_url_from_env(),
        serde=JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_CHECKPOINT_TYPES),
    )
