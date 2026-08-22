# Phase 10 — Model routing

Status: Complete

## Exit criterion

PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this phase:

> A request through the difficulty classifier is routed to the cheap-model path for a simple question and the strong-model path for a difficult one, and a forced timeout triggers the documented fallback strategy.

## Phase test

`tests/phases/test_phase_10.py`

## Tasks

- [x] Difficulty classifier + cheap/strong routing in `choose_model` (owner: `ai-orchestration`) — commit: `daa254b`
- [x] In-graph timeout + fallback and a per-chat cost budget (owner: `ai-orchestration`) — commit: `daa254b`
- [x] Model-comparison dashboard: `/models/comparison` + `/models` page (owner: `backend-api / frontend-web`) — commit: `daa254b`

## Notes on what was built, and what was not

**Routing lives in `choose_model`, not in new conditional edges.** The plan said
"LangGraph conditional edges for cheap/strong paths". Two near-identical generate
nodes joined by a branch would be ceremony: the alias is already carried on state
and `generate_answer` is alias-parameterised, so the routing decision is the
substance and a second generate node would duplicate ~80 lines to change one
argument. The branch that *does* earn its place — refuse vs continue — already
exists from Phase 4. The fallback is a loop inside one node rather than a graph
edge for the same reason: it must not re-stream, which is easier to guarantee in
one node than across two.

**Fallback and timeout are in the graph, not (only) in LiteLLM.** LiteLLM has its
own fallback/timeout config, and it is the right place for provider-level retries.
But the exit criterion is testable behaviour, and behaviour the graph owns is
behaviour a test can force without a running gateway. The graph-level fallback is
what the phase test drives; a LiteLLM-level one would be untestable here and is
left for a real deployment to add on top.

**The difficulty classifier is a heuristic, not a model.** docs/SPEC.md lists a
"difficulty classifier" and the obvious reading is a small model. That would put a
model call before every model call. The heuristic routes on question shape and is
a documented drop-in point for a model classifier — `classify_difficulty` is the
one function that would change.

## Known limits, carried forward

- **The classifier is keyword-and-length, so it misclassifies at the margins.** A
  terse but deep question ("UUID vs bigint?") lacks a marker word and routes
  cheap; a long but shallow paste routes strong. The bias is deliberately toward
  strong when any signal fires, because a misrouted-cheap hard question produces a
  bad answer while a misrouted-strong easy one only costs money.
- **The cost budget is a fixed ceiling over a fixed window.** No per-chat
  configuration, no carry-over. Enough to stop a runaway loop; not a billing
  system.
- **The dashboard has no chart.** It is a table. A `dataviz` pass would make the
  cost/latency trade-off legible at a glance, but the numbers are the substance
  and the table carries them.

## Not in this phase

- Local models — deferred to Phase 11
- Advanced learning features — deferred to Phase 12
