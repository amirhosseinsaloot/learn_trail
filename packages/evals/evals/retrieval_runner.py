"""Running the retrieval evaluation against the real library (Phase 8).

Separate from `retrieval_eval`, which holds the metrics and the dataset and needs
neither a database nor a gateway. This module is the part that has to talk to
both, and keeping the split means the metric definitions stay unit-testable.

**It retrieves through the real search path.** Not a reimplementation, not a
simplified query — `ai_core.retrieval.search`, the same function the endpoint
calls. A retrieval evaluation that exercised its own copy of the query would
measure code nobody runs.
"""

from __future__ import annotations

from ai_core.models.aliases import ModelAlias
from ai_core.models.gateway import answer as ask_model
from ai_core.retrieval import embed_query, search
from database.session import session_factory
from evals.retrieval_eval import RetrievalScore, load_retrieval_cases, score_case

#: How many passages to retrieve per case. Matches the ask endpoint's default, so
#: the numbers describe what the product actually does rather than a configuration
#: only the evaluation uses.
RETRIEVE_LIMIT = 5


async def run_retrieval() -> list[RetrievalScore]:
    """Score every retrieval case against the current library."""
    scores: list[RetrievalScore] = []

    async with session_factory()() as db:
        for case in load_retrieval_cases():
            vector = await embed_query(case.question)
            hits = await search(db, case.question, vector.vector, limit=RETRIEVE_LIMIT)

            contexts = [hit.content for hit in hits]
            # The answer is generated the same way the endpoint generates it, so
            # faithfulness measures the real behaviour. A hand-written answer here
            # would score the dataset rather than the product.
            generated = (
                (
                    await ask_model(
                        ModelAlias.LEARNING_FAST,
                        "Answer using only these passages; say so if they do not "
                        "contain the answer.\n\n"
                        + "\n\n".join(contexts)
                        + f"\n\nQuestion: {case.question}\n\nAnswer:",
                        max_tokens=400,
                    )
                ).text
                if hits
                else ""
            )

            scores.append(
                RetrievalScore(
                    case_id=case.id,
                    metrics=await score_case(case, contexts, generated),
                    # Deduplicated but order-preserving: several passages routinely
                    # come from one Learning, and the question being asked is
                    # "which documents", not "how many chunks".
                    retrieved_learnings=list(dict.fromkeys(hit.learning_title for hit in hits)),
                    expected_learnings=case.expected_learnings,
                )
            )
    return scores
