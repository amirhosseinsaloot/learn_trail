"""Persisting evaluation results (docs/SPEC.md §17, Phase 6).

Separate from the runner because the runner must work without a database: a
developer scoring a prompt change locally should not need Postgres up, and the
CI job that enforces the gate should not fail because a database was unreachable.
Storage is what makes regressions *queryable over time*, which is a different and
later need than "did this run pass".
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import EvaluationCase as EvaluationCaseRow
from database.models import EvaluationResult as EvaluationResultRow
from evals.datasets import all_cases
from evals.runner import MetricResult


async def sync_cases(db: AsyncSession) -> dict[str, EvaluationCaseRow]:
    """Register every dataset case, and return them keyed by `case_id`.

    Upsert by `case_id`, and note what is *not* done: a case whose file has been
    deleted keeps its row. The results referencing it are still history, and
    deleting the row would either orphan them or cascade away evidence of how the
    system used to perform.
    """
    existing = {
        row.case_id: row for row in (await db.execute(select(EvaluationCaseRow))).scalars().all()
    }
    for suite, case in all_cases():
        content = case.model_dump(mode="json")
        if row := existing.get(case.id):
            row.suite = suite
            row.content = content
        else:
            row = EvaluationCaseRow(case_id=case.id, suite=suite, content=content)
            db.add(row)
            existing[case.id] = row
    await db.commit()
    return existing


async def store_results(
    db: AsyncSession, results: Sequence[MetricResult], *, model_run_id: str | None = None
) -> int:
    """Write one row per metric verdict. Returns how many were written."""
    cases = await sync_cases(db)
    rows = [
        EvaluationResultRow(
            model_run_id=model_run_id,
            evaluation_case_id=cases[result.case_id].id if result.case_id in cases else None,
            evaluation_name=result.metric,
            evaluation_version=result.version,
            score=result.score,
            passed=result.passed,
            explanation=result.explanation,
        )
        for result in results
    ]
    db.add_all(rows)
    await db.commit()
    return len(rows)
