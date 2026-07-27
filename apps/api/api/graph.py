"""The compiled chat graph and its lifetime.

The graph is compiled once per process, not once per request: compilation is
pure setup, and the checkpointer it is compiled with owns a connection pool that
must outlive individual requests but not the application.

Held on `app.state` rather than in a module-level global so a test can substitute
one without monkeypatching an import, and so the pool is bound to the same event
loop the application runs on — a cached global would be reused across loops,
which is how "attached to a different loop" errors appear hours later.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request

from ai_core.graphs.chat import build_chat_graph
from ai_core.graphs.checkpointer import open_checkpointer
from ai_core.graphs.summary import build_summary_graph

#: Attribute name on `app.state`. One constant so the writer and the reader
#: cannot disagree about it.
GRAPH_ATTRIBUTE = "chat_graph"
SUMMARY_GRAPH_ATTRIBUTE = "summary_graph"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the checkpointer, compile the graph, and hold both for the process.

    `setup()` creates LangGraph's own checkpoint tables if they are absent. It is
    idempotent and runs on every boot deliberately: those tables are owned by
    LangGraph and are outside Alembic (see ai_core/graphs/checkpointer.py), so
    there is no migration that would otherwise create them.
    """
    async with open_checkpointer() as checkpointer:
        await checkpointer.setup()
        setattr(app.state, GRAPH_ATTRIBUTE, build_chat_graph().compile(checkpointer=checkpointer))
        # The summary graph shares the checkpointer, and needs it more: its
        # `await_approval` interrupt has nowhere to keep state without one, so an
        # approval could not survive a restart.
        setattr(
            app.state,
            SUMMARY_GRAPH_ATTRIBUTE,
            build_summary_graph().compile(checkpointer=checkpointer),
        )
        yield


def chat_graph(request: Request) -> Any:
    """The compiled graph for this request.

    Typed as `Any` because LangGraph's `CompiledStateGraph` generics do not
    survive a round trip through `app.state`, and a fabricated type annotation
    would be less honest than this one. The graph's *contract* is enforced where
    it matters — `ChatState` validates every node boundary.
    """
    graph = getattr(request.app.state, GRAPH_ATTRIBUTE, None)
    if graph is None:  # pragma: no cover - only reachable if lifespan did not run
        raise RuntimeError(
            "the chat graph is not compiled; the application lifespan did not run. "
            "A test client must run lifespan or set app.state.chat_graph itself."
        )
    return graph


def summary_graph(request: Request) -> Any:
    """The compiled summary graph for this request."""
    graph = getattr(request.app.state, SUMMARY_GRAPH_ATTRIBUTE, None)
    if graph is None:  # pragma: no cover - only reachable if lifespan did not run
        raise RuntimeError(
            "the summary graph is not compiled; the application lifespan did not run."
        )
    return graph
