# LearnTrail — AI Learning Workspace and AI Engineering Laboratory

**Tagline:** Ask. Understand. Approve. Remember.

## 1. Revised product definition

LearnTrail is a single-user AI learning application where you:

1. Start a persistent conversation about a subject.
2. Ask an initial question.
3. Continue asking follow-up questions.
4. Generate a structured summary when the session is complete.
5. Review and edit the AI-generated summary.
6. Approve and store it as a permanent learning.
7. Search, reopen and continue from previous learnings.
8. Delete or restore chats independently from approved summaries.

The application has no registration, login, roles, organizations or user-management functionality.

It runs as a private workspace for one person.

## 2. Secondary project objective

The product has two purposes:

### Product purpose

Create a useful personal learning journal.

### Engineering purpose

Learn how modern AI applications are designed, evaluated, secured, observed and improved.

The project should expose you to:

* Large-language-model APIs
* Model gateways
* Streaming
* Conversation memory
* Structured generation
* Agent orchestration
* Human-in-the-loop workflows
* Prompt management
* Input and output guardrails
* Moderation and PII detection
* AI evaluation
* Red teaming
* LLM observability
* OpenTelemetry
* Model comparison
* Retrieval-augmented generation
* Vector databases
* Prompt optimization
* Local models
* Cost and latency management

## 3. Core product loop

```text
Ask a question
      ↓
Receive an answer
      ↓
Ask follow-up questions
      ↓
AI maintains session context
      ↓
Finish the learning session
      ↓
Generate a structured summary draft
      ↓
Review, edit or regenerate
      ↓
Approve the summary
      ↓
Store it in My Learnings
      ↓
Search, revisit or continue learning
```

The user remains the authority over what becomes permanent knowledge.

## 4. Content states

### Chat

A chat is exploratory.

It can contain:

* Questions
* Incorrect assumptions
* Repeated explanations
* AI mistakes
* Examples
* Unresolved disagreements
* Irrelevant branches

### Summary draft

A summary draft is the model’s interpretation of the conversation.

It has not yet been accepted by the user.

### Approved learning

An approved learning is a user-reviewed record stored in the learning library.

```text
Chat = exploration

Summary draft = AI-generated interpretation

Approved learning = user-accepted knowledge
```

Approval is a human-in-the-loop checkpoint. The model may propose a summary, but it cannot approve the summary for the user.

---

# 5. Recommended architecture

```text
Next.js web interface
          ↓
FastAPI backend
          ↓
LangGraph learning workflow
          ↓
AI service and safety pipeline
          ↓
LiteLLM model gateway
          ↓
Cloud or local language models

Supporting systems:
- PostgreSQL
- pgvector
- OpenTelemetry
- Phoenix
- DeepEval
- Promptfoo
- NeMo Guardrails
- Guardrails AI
- LlamaIndex
- Ragas
- DSPy
```

Python should own the AI application layer because most orchestration, evaluation, safety and retrieval frameworks have mature Python integrations.

TypeScript should own the browser interface.

---

# 6. Recommended technology stack

## Frontend

### Next.js, React and TypeScript

Use the frontend for:

* Chat interface
* Token streaming
* Chat history
* Summary review
* My Learnings
* Search
* Evaluation dashboard
* Safety-event viewer
* Trace links
* Model-comparison screens

Suggested supporting libraries:

* Tailwind CSS
* shadcn/ui or another component library
* TanStack Query for server-state management
* Zod for frontend validation
* A Markdown renderer with code highlighting

The frontend should never receive model-provider credentials.

## Backend

### Python and FastAPI

FastAPI should expose endpoints for:

* Creating chats
* Sending messages
* Streaming answers
* Generating titles
* Generating summaries
* Approving learnings
* Editing learnings
* Deleting and restoring content
* Running evaluations
* Viewing model-run metadata

Use:

* Pydantic for request, response and AI-output schemas
* SQLAlchemy for persistence
* Alembic for database migrations
* Pytest for testing
* Ruff for linting
* mypy or Pyright for static checking

## Database

### PostgreSQL

Use PostgreSQL even though the project is single-user. It lets you learn relational modeling, migrations, indexing, full-text search, JSON storage and eventually vector retrieval.

Initial tables:

```text
chat
message
summary_draft
learning
learning_revision
tag
learning_tag
safety_event
model_run
evaluation_case
evaluation_result
prompt_version
```

There is no `user` table and no `user_id` column.

## Local development

Use Docker Compose for:

* PostgreSQL
* Backend
* Frontend
* Phoenix
* LiteLLM Proxy
* Optional local model runtime

This creates a reproducible AI-development environment.

---

# 7. AI framework responsibilities

Using many AI tools is useful only when each one has a clear responsibility. Avoid wrapping the same model call in five overlapping frameworks.

## LiteLLM — model gateway

Use LiteLLM as the boundary between your application and model providers.

Learn:

* Provider-independent model calls
* Model routing
* Fallback models
* Retry policies
* Token and cost tracking
* Rate limits
* Local-versus-cloud model switching
* Centralized provider configuration

LiteLLM exposes a gateway-style interface and supports model access, cost tracking, budgets, fallbacks and observability integrations.

Example model aliases:

```yaml
model_list:
  - model_name: learning-fast
    litellm_params:
      model: provider/small-model

  - model_name: learning-deep
    litellm_params:
      model: provider/reasoning-model

  - model_name: safety-judge
    litellm_params:
      model: provider/inexpensive-model
```

Your application should request `learning-fast`, not hard-code a provider-specific model name.

## LangGraph — workflow orchestration

Use LangGraph as the primary workflow runtime.

It is appropriate for:

* Stateful conversations
* Conditional routing
* Summary-generation workflows
* Human approval
* Retries
* Checkpointing
* Resuming interrupted workflows
* Explicit application state

LangGraph focuses on durable execution, streaming, persistence, memory and human-in-the-loop workflows.

Your main graph could be:

```text
receive_question
      ↓
input_safety_check
      ↓
select_model
      ↓
generate_answer
      ↓
output_safety_check
      ↓
persist_answer
      ↓
collect_feedback
```

The summary graph could be:

```text
load_chat
    ↓
prepare_context
    ↓
generate_structured_summary
    ↓
validate_summary
    ↓
run_summary_evaluations
    ↓
store_draft
    ↓
interrupt for user review
    ↓
approve, edit, regenerate or reject
```

## LangChain — integrations and primitives

Use LangChain selectively for:

* Model adapters
* Message abstractions
* Prompt templates
* Tool interfaces
* Output parsers
* Text splitting
* Framework integrations

Do not use a high-level prebuilt agent when a deterministic LangGraph workflow is clearer.

LangChain components integrate naturally with LangGraph, while LangGraph remains the orchestration layer.

## Pydantic AI — typed AI components

Use Pydantic AI for isolated, strongly typed AI operations such as:

* Summary generation
* Title generation
* Tag extraction
* Learning-topic classification
* Evaluation-result generation
* Safety-decision generation

Pydantic AI uses Python type hints and Pydantic models to define and validate structured agent outputs.

Example conceptual schema:

```python
class LearningSummary(BaseModel):
    title: str
    overview: str
    key_concepts: list[str]
    distinctions: list[str]
    examples: list[str]
    open_questions: list[str]
    suggested_tags: list[str]
    uncertainty_notes: list[str]
```

Do not make Pydantic AI and LangGraph compete for orchestration:

* LangGraph controls the workflow.
* Pydantic AI implements typed AI tasks inside graph nodes.

## LlamaIndex — retrieval and knowledge access

Add LlamaIndex after approved learnings begin accumulating.

Use it for:

* Indexing approved learnings
* Chunking and metadata management
* Semantic search
* Query engines
* Retrieval pipelines
* Source attribution
* Later document ingestion

LlamaIndex is designed for context augmentation, data-connected LLM applications, retrieval and workflows.

Do not use retrieval for the first chat version. Add it when the product needs to answer questions across previous learnings.

## DSPy — prompt and pipeline optimization

Use DSPy after you have:

* A stable task
* A dataset
* An evaluation metric
* A baseline score

Good DSPy targets include:

* Summary generation
* Suggested follow-up questions
* Topic classification
* Search-query rewriting
* Answer synthesis over previous learnings

DSPy optimizers can improve instructions and demonstrations against an explicit metric rather than relying entirely on manual prompt editing.

DSPy should be introduced late. Optimization without a trustworthy evaluation set only produces confidently optimized noise.

---

# 8. AI safety architecture

Safety should be a pipeline, not a single moderation call.

```text
User input
    ↓
Size and format validation
    ↓
Prompt-injection and jailbreak checks
    ↓
Content-safety classification
    ↓
PII and secret detection
    ↓
Model execution
    ↓
Structured-output validation
    ↓
Content-safety output check
    ↓
Policy and quality checks
    ↓
Display or block response
```

## Layer 1: Conventional validation

Before using an AI safety framework:

* Limit message length.
* Limit conversation-context size.
* Reject invalid encodings.
* Sanitize rendered Markdown and HTML.
* Restrict file types when uploads are added.
* Never execute generated code directly.
* Keep model credentials server-side.
* Use parameterized database queries.
* Set request timeouts.
* Enforce model-call budgets.

AI safety does not replace normal application security.

## Layer 2: Provider moderation

Run user inputs and generated outputs through the model provider’s moderation capability where available.

Record:

* Decision
* Categories
* Scores
* Policy version
* Whether the message was blocked
* Whether the user overrode a warning

Provider moderation is only one safety signal, not the entire policy engine.

## Layer 3: NeMo Guardrails

Use NeMo Guardrails for programmable conversational policies.

Candidate rails:

* Input rail
* Output rail
* Topic-control rail
* Jailbreak-detection rail
* PII rail
* Hallucination or fact-checking rail
* Tool-calling rail

NeMo Guardrails intercepts inputs and outputs and applies configurable policies. Its current documentation includes content safety, jailbreak protection, topic control, PII detection, agent security, tool calling, fact checking, evaluation and OpenTelemetry-based observability.

For this personal project, start with:

1. Prompt-injection detection
2. PII warning
3. High-stakes-topic warning
4. Output toxicity check

## Layer 4: Guardrails AI

Use Guardrails AI for validators attached to specific AI outputs.

Examples:

* Summary must not be empty.
* Title must remain below a length limit.
* Summary must preserve uncertainty.
* Summary must not introduce unsupported topics.
* PII must not be copied into an approved learning without warning.
* Required structured fields must exist.
* Unsafe links must be rejected.

Guardrails AI validators define validity criteria and configurable failure behavior for model outputs.

## Layer 5: Pydantic validation

Every structured model result should be parsed into a Pydantic schema.

Reject or retry when:

* Required fields are missing.
* Lists exceed configured limits.
* Values violate constraints.
* The model returns malformed output.
* Unknown fields appear where strict parsing is required.

Structured output improves format reliability, but it does not guarantee that the values are factually correct.

## Layer 6: Human approval

The user must approve:

* Learning summaries
* Changes to existing approved learnings
* Deletion of approved learnings
* Merging two learnings
* Any future external action

The AI must never silently promote an answer into approved knowledge.

## Safety event model

Store safety decisions separately:

```text
safety_event
- id
- chat_id
- message_id
- stage
- policy_name
- policy_version
- action
- severity
- categories
- explanation
- created_at
```

Possible actions:

```text
allow
allow_with_warning
redact
retry
block
require_review
```

---

# 9. Evaluation strategy

Evaluation should begin before the product feels “finished.”

## Evaluation layers

### Unit-level evaluation

Evaluate individual AI functions:

* Title generation
* Summary generation
* Tag extraction
* Question classification
* Safety classification
* Search-query generation

### Component evaluation

Evaluate:

* Answer-generation node
* Safety pipeline
* Summary pipeline
* Retrieval pipeline
* Model router

### Conversation evaluation

Evaluate multi-turn behavior:

* Does the assistant remember the topic?
* Does it answer the latest question?
* Does it contradict an earlier answer?
* Does it respond appropriately to corrections?
* Does it maintain the requested explanation depth?

### End-to-end evaluation

Evaluate the complete journey:

```text
Question
→ answer
→ follow-up
→ summary
→ approval candidate
```

## DeepEval

Use DeepEval as the Python-native test framework.

It supports pytest-style LLM tests, conversational evaluation and metrics for areas such as task completeness, relevancy, hallucination, summarization, toxicity and bias.

Create tests such as:

```text
test_answer_relevance
test_answer_does_not_ignore_correction
test_summary_is_faithful_to_chat
test_summary_preserves_uncertainty
test_summary_excludes_unrelated_content
test_unsafe_input_is_blocked
test_pii_is_not_silently_persisted
```

## Promptfoo

Use Promptfoo for declarative prompt comparison, regression testing, model comparison and adversarial red teaming.

Promptfoo supports CLI-based evaluation, CI integration and red-team testing of LLM applications.

Use it to compare:

* Prompt version A versus B
* Small model versus large model
* Cloud model versus local model
* Guardrails enabled versus disabled
* Different system instructions
* Different context-window strategies

Red-team scenarios should include:

* Prompt injection
* Jailbreak attempts
* Hidden-instruction extraction
* PII leakage
* System-prompt requests
* Excessive agency
* Unsafe high-stakes advice
* Encoded attacks
* Multi-turn policy bypasses

## Ragas

Introduce Ragas when you add semantic retrieval over approved learnings.

Use it to evaluate:

* Retrieval relevance
* Context recall
* Context precision
* Answer faithfulness
* Answer relevance

Ragas is specifically designed for evaluating retrieval and generation pipelines and supports experiment-based iteration over datasets.

## Human evaluation

AI judges are not sufficient.

Create a small review interface where you score:

* Correctness
* Usefulness
* Clarity
* Appropriate depth
* Faithfulness to the conversation
* Safety
* Whether you would approve the summary

Store both numeric ratings and written notes.

## Product-derived evaluation signals

Your application naturally generates valuable evaluation data:

* Summary approved without editing
* Summary approved after editing
* Summary regenerated
* Summary rejected
* Answer retried
* Answer marked helpful
* Learning later corrected
* Safety warning overridden
* Chat abandoned

One particularly useful metric is **summary edit distance**: how much the approved version differs from the original AI-generated draft.

A high edit distance indicates that the summarization prompt or model may need improvement.

---

# 10. Evaluation dataset

Create a versioned dataset in the repository:

```text
evals/
├── conversations/
├── summaries/
├── safety/
├── retrieval/
├── adversarial/
└── fixtures/
```

Each case can contain:

```json
{
  "id": "summary-001",
  "messages": [
    {
      "role": "user",
      "content": "What is a vector database?"
    }
  ],
  "grading_notes": [
    "Must explain embeddings",
    "Must distinguish semantic and exact search",
    "Must not claim relational databases are unnecessary"
  ],
  "forbidden_claims": [
    "Vector databases guarantee correct answers"
  ],
  "tags": [
    "summary",
    "databases"
  ]
}
```

Dataset sources:

* Handwritten cases
* Real chats you explicitly add
* Previous failures
* Safety attacks
* Model-generated synthetic cases
* Edge cases found in traces

Never make every production chat automatically part of the permanent evaluation dataset. Curate it intentionally.

---

# 11. Observability architecture

## OpenTelemetry

Instrument the application using OpenTelemetry-compatible traces.

Trace:

* HTTP request
* LangGraph run
* Each graph node
* Safety checks
* Model calls
* Retries
* Token usage
* Latency
* Database operations
* Summary generation
* Evaluation calls

Keep your instrumentation vendor-neutral.

## Phoenix

Use Phoenix as the first observability backend because it supports AI-focused tracing, evaluation and experimentation through OpenTelemetry and OpenInference-compatible instrumentation.

A trace should resemble:

```text
chat.request
├── load_conversation
├── input_guardrails
│   ├── moderation
│   ├── injection_check
│   └── pii_check
├── context_builder
├── llm.generate
├── output_guardrails
├── persist_message
└── async_evaluations
```

Capture:

* Trace ID
* Chat ID
* Prompt version
* Model alias
* Actual provider model
* Temperature
* Input tokens
* Output tokens
* Estimated cost
* First-token latency
* Total latency
* Retries
* Guardrail decisions
* Evaluation scores
* Error type

Do not store secrets or unnecessary sensitive content in traces.

## Langfuse comparison phase

After learning Phoenix, reproduce the same instrumentation in Langfuse as a comparison exercise.

Langfuse provides LLM-specific tracing with prompts, responses, tool calls, token usage, costs, scores, datasets, experiments and prompt management.

Do not permanently run two overlapping observability platforms unless you are explicitly comparing them. Instrument with OpenTelemetry once and keep the backend replaceable.

---

# 12. Prompt management

Do not leave prompts scattered through Python files.

Store prompt definitions with:

```text
name
version
purpose
template
variables
model_settings
created_at
evaluation_score
status
```

Suggested prompts:

```text
learning_answer
chat_title
learning_summary
tag_suggestion
summary_faithfulness_judge
answer_relevance_judge
safety_classifier
retrieval_query_rewriter
```

Use lifecycle states:

```text
draft
candidate
active
retired
```

Every trace and evaluation result should record the prompt version.

Do not promote a candidate prompt merely because a few examples look better. Require it to pass the evaluation suite.

---

# 13. Model strategy

Use several model classes deliberately.

## Fast model

Use for:

* Title generation
* Tag suggestions
* Classification
* Simple safety checks
* Query rewriting

## Strong general model

Use for:

* Main learning answers
* Summary generation
* Difficult explanations

## Judge model

Use for:

* Evaluation
* Faithfulness checks
* Safety classification

The judge should not always be the same model that generated the answer.

## Local model

Later, add Ollama or vLLM behind LiteLLM to learn:

* Local inference
* Quantization
* Hardware limitations
* Latency and throughput
* Cloud-versus-local evaluation
* Privacy trade-offs

Do not create a separate application path for local models. Keep both local and cloud models behind the same gateway.

---

# 14. Conversation memory

Use three memory layers.

## Raw conversation memory

The complete persisted chat stored in PostgreSQL.

## Working context

The subset of conversation passed to the model for the current answer.

Possible strategies:

* Full history for short chats
* Recent-message window
* Previous-summary plus recent messages
* Relevance-selected messages

## Approved long-term memory

Only approved learnings should be treated as durable user knowledge.

Do not automatically create long-term memory from every message.

Later, LangGraph’s persistence and memory mechanisms can support thread state, checkpoints and long-term memory workflows.

---

# 15. Incremental implementation roadmap

## Phase 0 — Development environment

### Build

* Monorepo
* Next.js frontend
* FastAPI backend
* PostgreSQL
* Alembic
* Docker Compose
* Pytest
* Linting and type checking

### AI components

None yet.

### Learning objective

Understand the application boundary before introducing AI abstractions.

---

## Phase 1 — Basic AI chat

### Build

* Create chat
* Persist messages
* Stream answers
* Resume conversations
* Rename chats
* Soft-delete chats

### AI stack

* LiteLLM
* One cloud model
* Pydantic request and response models

### Learn

* Model APIs
* Streaming
* Tokens
* Context windows
* Temperature
* Timeouts
* Retries
* Provider abstraction

### Exit criterion

You can stop the application, restart it and continue a previous conversation.

---

## Phase 2 — LangGraph workflow

### Replace the direct model call with

```text
validate_input
→ build_context
→ choose_model
→ generate_answer
→ persist
```

### AI stack

* LangGraph
* LangChain model/message integrations
* LangGraph PostgreSQL checkpointer where appropriate

### Learn

* Graph state
* Nodes
* Edges
* Conditional routing
* Checkpoints
* Workflow retries
* Human interruption
* State persistence

### Exit criterion

Each chat request is visible as a deterministic graph execution.

---

## Phase 3 — Structured summary generation

### Build

* Finish and summarize
* Typed summary schema
* Summary draft
* Edit
* Regenerate
* Approve
* Learning library
* Revision history

### AI stack

* Pydantic AI
* Pydantic structured output
* LangGraph approval interrupt
* Guardrails AI schema validators

### Learn

* Structured generation
* Validation
* Retries
* Human-in-the-loop
* Model-generated drafts versus approved data

### Exit criterion

Malformed or incomplete summaries are rejected before persistence.

---

## Phase 4 — Safety pipeline

### Build

* Input moderation
* Output moderation
* Prompt-injection checks
* PII warning
* High-stakes-topic warning
* Safety-event persistence
* Block and warning UI

### AI stack

* NeMo Guardrails
* Guardrails AI
* Provider moderation
* Custom Pydantic validators

### Learn

* Policy design
* Input rails
* Output rails
* Redaction
* Blocking
* Warnings
* False positives
* Safety auditing

### Exit criterion

Every model interaction has an explicit, testable safety path.

---

## Phase 5 — Observability

### Build

* Distributed trace IDs
* Model latency metrics
* Token and cost recording
* Graph-node spans
* Guardrail spans
* Prompt-version metadata
* Trace viewer links

### AI stack

* OpenTelemetry
* OpenInference instrumentation
* Phoenix

### Learn

* Traces
* Spans
* Attributes
* Metrics
* Logs
* LLM-specific telemetry
* Cost and latency analysis

### Exit criterion

A poor answer can be traced through context construction, model execution, guardrails and persistence.

---

## Phase 6 — Evaluation-driven development

### Build

* Golden conversation dataset
* Summary dataset
* Safety dataset
* Evaluation runner
* Regression thresholds
* Evaluation-result storage
* Local evaluation report

### AI stack

* DeepEval
* Promptfoo
* Phoenix experiments
* Pytest

### Initial metrics

* Answer relevance
* Conversation completeness
* Summary faithfulness
* Summary completeness
* Hallucination
* Toxicity
* Safety-policy compliance
* Latency
* Cost

### Exit criterion

Prompt or model changes cannot be merged without running the evaluation suite.

---

## Phase 7 — Red teaming

### Build

* Adversarial dataset
* Prompt-injection tests
* Jailbreak tests
* PII-leakage tests
* System-prompt extraction tests
* Multi-turn attack tests
* CI safety gate

### AI stack

* Promptfoo red-team
* NeMo Guardrails evaluation
* DeepEval safety metrics

### Learn

* Threat modeling
* Adversarial testing
* Attack success rate
* Safety regression
* Defense-in-depth

### Exit criterion

You can measure whether a safety change improves or harms the system.

---

## Phase 8 — Search across approved learnings

### Build

* PostgreSQL full-text search
* Embeddings
* pgvector
* Semantic search
* Hybrid search
* Ask across My Learnings
* Citations to stored learnings

### AI stack

* LlamaIndex
* Embedding model
* pgvector
* Ragas

### Learn

* Chunking
* Embeddings
* Similarity search
* Metadata filtering
* Reranking
* Retrieval evaluation
* Grounded generation

### Exit criterion

Answers based on previous learnings identify exactly which approved learning supplied the context.

---

## Phase 9 — Prompt optimization

### Build

* Select one stable AI task
* Define a metric
* Create training and validation sets
* Optimize the task
* Compare optimized and manual prompts

### AI stack

* DSPy
* DeepEval or custom evaluation metric
* Phoenix experiment tracking

### Recommended first task

Optimize summary generation for:

* Faithfulness
* Completeness
* Concision
* Low user edit distance

### Exit criterion

The optimized program performs better on held-out examples, not only its optimization set.

---

## Phase 10 — Model routing

### Build

* Difficulty classifier
* Cheap-model path
* Strong-model path
* Fallback strategy
* Timeout strategy
* Cost budget
* Model-comparison dashboard

### AI stack

* LiteLLM routing
* LangGraph conditional edges
* Phoenix traces
* DeepEval comparisons

### Learn

* Quality-versus-cost trade-offs
* Cascading models
* Fallbacks
* Routing accuracy
* Service-level objectives

---

## Phase 11 — Local models

### Build

* Ollama or vLLM
* Local model registered in LiteLLM
* Cloud-versus-local benchmark
* Privacy mode
* Offline development mode

### Learn

* Model serving
* Quantization
* GPU and CPU constraints
* Throughput
* Context limitations
* Model portability

---

## Phase 12 — Advanced learning features

Only after the platform is well evaluated:

* Quiz generation
* Flashcards
* Spaced repetition
* Knowledge graph
* Learning-path recommendations
* Document ingestion
* Voice interface
* MCP-based tools
* Export to Markdown or PDF

---

# 16. Suggested repository structure

```text
learntrail/
├── apps/
│   ├── web/
│   └── api/
├── packages/
│   ├── ai_core/
│   │   ├── graphs/
│   │   ├── agents/
│   │   ├── prompts/
│   │   ├── schemas/
│   │   ├── safety/
│   │   ├── retrieval/
│   │   ├── models/
│   │   └── telemetry/
│   ├── evals/
│   │   ├── datasets/
│   │   ├── metrics/
│   │   ├── judges/
│   │   ├── red_team/
│   │   └── reports/
│   └── database/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── ai/
│   ├── safety/
│   └── end_to_end/
├── prompts/
├── infra/
│   ├── docker/
│   ├── litellm/
│   ├── phoenix/
│   └── otel/
└── docker-compose.yml
```

---

# 17. Simplified data model

## Chat

```text
id
title
status
created_at
updated_at
deleted_at
```

## Message

```text
id
chat_id
role
content
sequence_number
model_run_id
created_at
```

## SummaryDraft

```text
id
chat_id
title
structured_content
status
prompt_version
model_run_id
created_at
updated_at
```

## Learning

```text
id
source_chat_id
title
structured_content
approved_at
created_at
updated_at
deleted_at
```

## LearningRevision

```text
id
learning_id
revision_number
structured_content
change_source
created_at
```

## ModelRun

```text
id
trace_id
operation
model_alias
provider_model
prompt_version
input_tokens
output_tokens
estimated_cost
latency_ms
status
created_at
```

## EvaluationResult

```text
id
model_run_id
evaluation_name
evaluation_version
score
passed
explanation
created_at
```

## SafetyEvent

```text
id
chat_id
message_id
stage
policy
action
severity
details
created_at
```

---

# 18. What not to implement initially

Even in a learning-focused project, avoid introducing complexity without a measurable purpose.

Do not begin with:

* Authentication
* Multiple users
* Organizations
* Permissions
* Kubernetes
* Microservices
* Multi-agent swarms
* Autonomous browsing
* Automatic code execution
* Knowledge graphs
* Fine-tuning
* Multiple vector databases
* Two permanent observability platforms
* Several competing orchestration frameworks

The goal is to add one new AI concept per phase and evaluate its effect.

---

# 19. Recommended initial stack

Start with this exact subset:

```text
Frontend:
- Next.js
- React
- TypeScript
- Tailwind CSS

Backend:
- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

Persistence:
- PostgreSQL

AI:
- LiteLLM
- LangGraph
- LangChain integrations

Observability:
- OpenTelemetry
- Phoenix

Testing:
- Pytest
- DeepEval

Infrastructure:
- Docker Compose
```

Add these after the core chat works:

```text
Structured tasks:
- Pydantic AI

Safety:
- NeMo Guardrails
- Guardrails AI
- Provider moderation

Security testing:
- Promptfoo

Retrieval:
- LlamaIndex
- pgvector
- Ragas

Optimization:
- DSPy

Local models:
- Ollama or vLLM
```

---

# 20. First implementation milestone

The first milestone should demonstrate the complete infrastructure path without implementing the complete product.

```text
Browser
   ↓
Next.js chat page
   ↓
FastAPI streaming endpoint
   ↓
LangGraph
   ↓
LiteLLM
   ↓
Language model
   ↓
Phoenix trace
   ↓
PostgreSQL persistence
```

It should support:

1. Create a chat.
2. Send a question.
3. Stream the response.
4. Persist both messages.
5. Resume the chat.
6. Record a complete trace.
7. Run one answer-relevance evaluation.
8. Delete and restore the chat.

After this milestone is reliable, implement summary generation and approval.

# Final definition

**LearnTrail is a single-user AI learning workspace and practical AI-engineering laboratory. It converts persistent learning conversations into user-approved knowledge while providing a structured environment for learning orchestration, structured generation, safety, evaluation, red teaming, retrieval, model routing and LLM observability.**
