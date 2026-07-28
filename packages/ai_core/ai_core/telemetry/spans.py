"""The trace vocabulary (docs/SPEC.md §11).

The span names live in one module, apart from the code that emits them, for the
reason every shared vocabulary does: a name that appears in the graph, in the
endpoint and in the phase test as three separate string literals is three names
that can drift. Here they are one.

**Why these names and not the node names.** The graph's nodes are called
`input_safety_check`, `build_context`, `persist`; docs/SPEC.md §11 draws the
trace it wants with `input_guardrails`, `context_builder`, `persist_message`.
Rather than pick a winner and quietly diverge from one document or the other,
`SPAN_FOR_NODE` states the translation explicitly — so a reader comparing the
SPEC's diagram to a real trace finds the shape it promised, and a reader in the
graph can see which span a node produces without guessing.
"""

from __future__ import annotations

from typing import Final

#: The root span for one answered question. Everything else nests under it.
CHAT_REQUEST: Final = "chat.request"

#: Reading the conversation out of the database, before the graph starts.
LOAD_CONVERSATION: Final = "load_conversation"

#: The four stages the Phase 5 exit criterion names, in order.
INPUT_GUARDRAILS: Final = "input_guardrails"
CONTEXT_BUILDER: Final = "context_builder"
LLM_GENERATE: Final = "llm.generate"
OUTPUT_GUARDRAILS: Final = "output_guardrails"
PERSIST_MESSAGE: Final = "persist_message"

#: Summary generation is the system's other model call, and gets its own root.
SUMMARY_REQUEST: Final = "summary.request"

#: Graph node name -> span name. Nodes absent from this map emit no span of
#: their own: `validate_input` and `choose_model` are pure, sub-millisecond and
#: allocate nothing, so a span for each would triple the trace's size to say
#: "this returned immediately, again". They become interesting in Phase 10, when
#: `choose_model` starts making a real decision, and that is when they get spans.
SPAN_FOR_NODE: Final[dict[str, str]] = {
    "input_safety_check": INPUT_GUARDRAILS,
    "build_context": CONTEXT_BUILDER,
    "generate_answer": LLM_GENERATE,
    "output_safety_check": OUTPUT_GUARDRAILS,
    "persist": PERSIST_MESSAGE,
}

#: The four stages docs/SPEC.md names in the Phase 5 exit criterion — "context
#: construction, model execution, guardrails and persistence" — as the spans
#: that make each one visible. The phase test reads this rather than a copy.
CRITERION_STAGES: Final[dict[str, tuple[str, ...]]] = {
    "context construction": (LOAD_CONVERSATION, CONTEXT_BUILDER),
    "model execution": (LLM_GENERATE,),
    "guardrails": (INPUT_GUARDRAILS, OUTPUT_GUARDRAILS),
    "persistence": (PERSIST_MESSAGE,),
}


class Attr:
    """Attribute keys, so a typo cannot silently create a second attribute.

    Split by origin. The `openinference.*` and `llm.*` names are OpenInference's
    semantic conventions, which is what lets a trace viewer render a model call
    as a model call rather than as an anonymous span with some strings on it.
    The `learntrail.*` names are ours, for facts no convention covers — which
    chat this was, which policy version judged it.

    docs/SPEC.md §11: "Do not store secrets or unnecessary sensitive content in
    traces." There is deliberately no attribute here for a matched PII value, a
    gateway key, or a raw provider payload.
    """

    # Ours.
    CHAT_ID: Final = "learntrail.chat_id"
    MESSAGE_ID: Final = "learntrail.message_id"
    MODEL_ALIAS: Final = "learntrail.model_alias"
    PROMPT_VERSION: Final = "learntrail.prompt_version"
    SAFETY_ACTION: Final = "learntrail.safety.action"
    SAFETY_CATEGORIES: Final = "learntrail.safety.categories"
    SAFETY_POLICY_VERSION: Final = "learntrail.safety.policy_version"
    SAFETY_BLOCKED: Final = "learntrail.safety.blocked"
    CONTEXT_MESSAGES: Final = "learntrail.context.message_count"
    # S105 fires on the word "token" here; this is a *model* token, not a credential.
    FIRST_TOKEN_MS: Final = "learntrail.first_token_ms"  # noqa: S105
    ESTIMATED_COST: Final = "learntrail.estimated_cost_usd"

    # OpenInference conventions.
    SPAN_KIND: Final = "openinference.span.kind"
    PROVIDER_MODEL: Final = "llm.model_name"
    INPUT_TOKENS: Final = "llm.token_count.prompt"
    OUTPUT_TOKENS: Final = "llm.token_count.completion"
    TOTAL_TOKENS: Final = "llm.token_count.total"
