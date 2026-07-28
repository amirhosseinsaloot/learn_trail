# Phase 8 — Search across approved learnings

Status: Complete

## Exit criterion

Exit criterion (verbatim, docs/SPEC.md):

> Answers based on previous learnings identify exactly which approved learning supplied the context.

## Phase test

`tests/phases/test_phase_8.py`

## Tasks

- [x] Chunking + embedding pipeline for approved learnings via LlamaIndex (owner: `ai-orchestration`) — commit: `14ddf42`
- [x] pgvector migration + hybrid (full-text + semantic) search endpoint (owner: `backend-api`) — commit: `8832d90`, `14ddf42`
- [x] Retrieval evaluation: precision, recall, faithfulness (owner: `ai-orchestration`) — commit: `PENDING`
      **Not via Ragas.** docs/SPEC.md §9 names it and that was the intent, but
      ragas 0.4.3 cannot be imported at all: every entry point routes through
      `ragas.llms.base`, which hard-imports
      `langchain_community.chat_models.vertexai` — a module current
      `langchain-community` no longer provides. Making it work means pinning a
      dated dependency around an upstream bug and pulling a very large tree in
      for three prompts. Ragas's metric definitions are implemented directly
      instead, which also keeps the judge on the gateway where invariant #2 says
      model calls belong. The dataset and thresholds transfer unchanged if ragas
      is fixed.

## What the criterion actually rests on

Attribution is a fact about *retrieval*, not a claim in the model's prose. The
answer is built from chunks, each chunk carries the id of the Learning it came
from, and the citation list is those ids. Nothing parses "[1]" markers, so there
is no path by which the model can invent a source or forget one — the failure is
designed out rather than tested for.

`tests/phases/test_phase_8.py` was mutation-checked against four breaks —
dropping `learning_id` from the citation, making citations optional in the
response schema, pointing the excerpt at the title instead of the retrieved text,
and stopping fusion preferring agreement. All four fail it.

## Live results

Three Learnings seeded through the real approval flow, 15 chunks:

    "difference between an index and a primary key"  -> 5 citations, all to the
                                                        index Learning, one found
                                                        by both search halves
    "replace Postgres with a vector database?"       -> 5 citations, all to the
                                                        vector Learning
    "How do I make sourdough bread?"                 -> grounded: false, no
                                                        citations, no model call

Retrieval evaluation, against the same library:

    ret-001 (direct)      precision 0.80  recall 1.00  faithfulness 1.00
    ret-002 (paraphrased) precision 0.80  recall 1.00  faithfulness 1.00
    ret-003 (two sources) precision 0.60  recall 1.00  faithfulness 1.00

## Known limits, carried forward

- **The distance floor is tuned to one embedding model and one small library.**
  0.80 sits in a gap measured at three Learnings. Re-derive it after changing the
  embedding model, and re-check it as the library grows — a larger library has
  more chances to put something spurious inside the floor.
- **Chunking discards the section label.** `Chunk.section` exists and is not
  persisted, so filtered search ("only distinctions") is not yet possible.
- **Re-indexing is per-Learning and synchronous.** Approving blocks on an
  embedding call. Fine at this scale; a library of thousands would want a queue.
- **A failed re-index is silent.** `_reindex_quietly` swallows it so an approval
  never fails because the gateway was down — the trade is that a Learning can be
  approved and not searchable, visible only in the trace. `POST /learnings/reindex`
  is the recovery, which is why it is not optional.
- [x] Ask-across-My-Learnings UI with citations to the source learning (owner: `frontend-web`) — commit: `PENDING`

## Not in this phase

- DSPy prompt optimization — deferred to Phase 9
- Model routing — deferred to Phase 10
