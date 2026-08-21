"""The model-comparison dashboard (docs/SPEC.md §15, Phase 10).

Reads `model_run` — the cost/latency record every generation already writes since
Phase 5 — and aggregates it per alias. This is what makes the routing decision
answerable after the fact: *did* the strong model cost more, was it slower, how
often did a fallback fire. A router you cannot see the effect of is a router you
cannot tune.

Read-only, and no model call: it is arithmetic over rows. There is no
corresponding write endpoint because there is nothing to write — the rows are a
byproduct of answering.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Float, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import ModelComparison, ModelUsage
from database.models import ModelRun
from database.session import session

router = APIRouter(prefix="/models", tags=["models"])

Session = Annotated[AsyncSession, Depends(session)]


@router.get("/comparison")
async def model_comparison(
    db: Session,
    window_hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24 * 7,
) -> ModelComparison:
    """Per-alias usage over a rolling window.

    `window_hours` defaults to a week, which is long enough that a lightly-used
    library still has rows to compare and short enough that a routing change made
    yesterday is not drowned by a month of the old behaviour.

    Latency and cost are averaged in the database rather than in Python: the rows
    are the authority, and pulling thousands of them across the wire to average
    them here would be the dashboard paying for its own decoration.
    """
    since = func.now() - timedelta(hours=window_hours)

    rows = (
        await db.execute(
            select(
                ModelRun.model_alias,
                func.count().label("runs"),
                func.coalesce(func.sum(ModelRun.estimated_cost), 0).label("total_cost"),
                func.coalesce(func.avg(ModelRun.latency_ms).cast(Float), 0.0).label("avg_latency"),
                func.coalesce(func.sum(ModelRun.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(ModelRun.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(case((ModelRun.status == "blocked", 1), else_=0)), 0).label(
                    "blocked"
                ),
            )
            .where(ModelRun.created_at >= since)
            .group_by(ModelRun.model_alias)
            .order_by(func.count().desc())
        )
    ).all()

    usage = [
        ModelUsage(
            model_alias=row.model_alias,
            runs=row.runs,
            total_cost=float(row.total_cost),
            avg_latency_ms=round(row.avg_latency, 1),
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            blocked=int(row.blocked or 0),
        )
        for row in rows
    ]
    return ModelComparison(window_hours=window_hours, usage=usage)
