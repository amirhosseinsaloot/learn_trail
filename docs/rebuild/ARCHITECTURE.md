# Nuroli Architecture

Status: **Phases 1 and 2 complete and approved by the product owner.** Every
decision in the register (section 3) is confirmed. Changes require a new register
entry. Phase 3 (development setup) starts only on explicit authorization.

Branch: `rebuild/v1`. Companion documents: [DESIGN.html](DESIGN.html) (product
experience) and [IMPLEMENTATION.md](IMPLEMENTATION.md) (execution plan and
ticket backlog, produced in Phase 2).

How to read this document: sections 1 to 3 define what is being built and why.
Sections 4 to 9 define the domain and the contracts between layers and between
the browser and the API. Sections 10 to 19 define persistence, deployment,
configuration, security, and operations. Sections 20 to 23 define delivery,
agent boundaries, extension points, and alternatives.

---

## 1. Product goals, scope, and non-goals

### 1.1 Purpose

Nuroli supports a personal learning loop: ask a model questions, research facts
with visible sources, continue a deep discussion, turn the useful conclusions
into a reviewed summary, keep that summary as knowledge, and ask questions
across saved knowledge later. People install their own copy with Docker Compose
and connect one model endpoint of their choice.

### 1.2 Goals

- A working, secure, self-hosted product with the smallest coherent
  architecture that supports the agreed flows.
- Every product rule that matters (ownership, confirmation before save,
  summary-only retrieval, model attribution, credentials never in the browser)
  is enforced on the server and covered by tests.
- Small enough modules and tickets that weaker implementation models can
  deliver them one at a time without inventing architecture.
- A versioned API that a future mobile client can use unchanged.

### 1.3 V1 scope (confirmed, R-01)

1. Registration and login with Google sign-in or email and password.
2. Multiple users per installation with strict ownership isolation.
3. One operator-configured model connection using the OpenAI-compatible chat
   completions protocol.
4. Conversations with streamed replies, stop, and retry.
5. Per-message web research with clickable sources.
6. Summary generation, review, editing, and explicit confirmation before save.
7. A knowledge library of confirmed summaries with archive.
8. Knowledge questions answered only from confirmed summaries, with citations.
9. Reopening the full source conversation from a summary.
10. Docker Compose installation with backups and restore.

### 1.4 Explicitly deferred (not in v1)

| Capability | Why deferred | Extension point kept |
| --- | --- | --- |
| Per-reply model choice and multiple providers | One connection must work first | `model_name` recorded on every assistant message; `ChatModelPort` boundary |
| Anthropic Messages or other protocols | OpenAI-compatible covers the gateways and local runtimes | Second adapter behind the same port |
| Embedding-based retrieval | Chat-only model guarantee | Search method on the summary repository |
| Page fetching for research | SSRF surface and extraction work | Same research port |
| Email verification, password reset by email | No mail server in local installs | Operator reset command now |
| Google and password account linking | Account-takeover risk without verified email | One method per email now |
| Admin settings UI | Operator config flags suffice | `role` column exists |
| Stored knowledge-question history | Not needed for the loop | Answers stream and are not persisted |
| Hosted accounts, credits, billing | Later phase | Usage columns on messages; ownership on every record |
| Mobile client | Later phase | Versioned API; bearer session variant on the same sessions table |
| Public sample or demo pages | Removed (R-04) | None |
| Metrics stack, tracing | Logs and health endpoints suffice | Structured logs with request ids |

---

## 2. Users, roles, ownership, and trust boundaries

**Installation operator.** Runs Docker Compose, owns the environment file with
the model key, search key, Google client secret, and database password. Uses
operator commands inside the API container (password reset, model check).
Never authenticates through the API as a special role.

**User.** Registers or signs in. Owns conversations, messages, summaries, and
versions. Two roles exist: `admin` (the first account) and `member`. In v1 the
admin role grants nothing extra; it is recorded for later.

**Ownership rule.** Every conversation and summary has an `owner_id`. Every
read and write passes the acting user id from the verified session into the
repository query. There is no endpoint that lists or reads another user's data.
A missing or foreign record returns 404, never 403, so ids cannot be probed.

**Trust boundaries.**

| Boundary | Trusted | Untrusted |
| --- | --- | --- |
| Browser to API | Nothing except the session cookie after verification | All request bodies, ids, headers, and query strings |
| API to model endpoint | The configured base URL and key | All model output |
| API to search provider | The configured endpoint and key | All result text and URLs |
| Model prompt | System instructions written by the backend | User text, transcripts, search snippets, summaries |
| Environment file | The operator | Never exposed through the API |

---

## 3. Decision register

Decisions confirmed by the product owner in the Phase 1 planning session.
Decisions applied directly from the rebuild brief without a separate question:
per-reply model choice deferred; no reuse of the previous application;
operator-configured model connection; documentation stays focused on the
product, users, engineering, security, and implementation.

| ID | Decision | Status | One-line reason |
| --- | --- | --- | --- |
| R-01 | Product name is Nuroli. V1 scope as in section 1.3; deferred list as in section 1.4. | confirmed | Smallest scope that delivers the complete learning loop end to end. |
| R-02 | Planning files stay at `docs/rebuild/DESIGN.html`, `docs/rebuild/ARCHITECTURE.md`, `docs/rebuild/IMPLEMENTATION.md`. | confirmed | Already tracked there; keeps the repository root free for code and setup in Phase 3. |
| R-03 | No temporary directory inside the repository during Phases 1 and 2; drafts use the harness scratchpad outside the repo; `.gitignore` is created in Phase 3. | confirmed | Keeps the branch limited to the three planning files. |
| R-04 | The public synthetic sample-data deployment is removed. No demo pages with simulated responses exist in any release. | confirmed | V1 is a production-ready product; a fake demo surface adds a delivery path without user value. |
| R-05 | Knowledge retrieval uses PostgreSQL full-text search over the current confirmed version of each summary, owner-scoped, ranked, updated inside the confirm transaction. No pgvector, no embedding endpoint. Extension point: the summary repository search method. | confirmed | The first model connection guarantees chat only; lexical search needs no second model capability or extra image. |
| R-06 | The single v1 model adapter implements OpenAI-compatible chat completions with streaming. Configuration: base URL, model name, API key, timeouts, output token limit. No provider switch, no capability negotiation. | confirmed | One protocol covers OpenRouter, OpenAI, Ollama, vLLM, and LM Studio. |
| R-07 | Web research uses search-API results only (title, URL, publisher, snippet). The backend never fetches linked pages in v1. Outbound calls are limited to the configured model host and search host. | confirmed | Closes the SSRF surface by construction. |
| R-08 | The v1 search adapter is Tavily. Research is disabled cleanly when no key is configured. | confirmed | Free monthly quota without a card, snippet-ready JSON, no extra containers. |
| R-09 | Research is a per-message user toggle. When on, the backend makes one bounded non-streamed model call to rewrite the question into a search query, performs one search, then streams the reply with attached sources. The model never decides to search. | confirmed | Chat-only models cannot be relied on for tool calling; raw follow-ups make poor queries. |
| R-10 | Backend domain modules: Identity and Access, Conversations, Knowledge. Ports with one adapter each: chat model, web search. Platform module: settings, database, migrations, health, logging, rate limits, operator commands. Web research is a port used by Conversations, not a bounded context. Capture and retrieval share the Knowledge module. | confirmed | Fewest modules that still enforce every product rule. |
| R-11 | Aggregates: User; Conversation with Message entities; Summary with SummaryVersion entities. Invariants in section 4.3. Sessions are an infrastructure table outside the User aggregate. | confirmed | Three roots cover every product rule. |
| R-12 | Reply streaming uses Server-Sent Events framing over a POST fetch stream. Event lifecycle: start, research, sources, delta, end, error. No WebSocket. | confirmed | Standard framing that passes through nginx without extra services. |
| R-13 | Sessions are opaque random tokens whose hash is stored in a database table with expiry and revocation, sent as an HttpOnly, Secure, SameSite=Lax cookie. CSRF: state-changing requests must carry a matching Origin header and the custom header `X-Requested-With: nuroli`. Logout deletes the row. | confirmed | Revocable by design; JWT would need the same table to revoke. |
| R-14 | The first account created on a fresh installation receives the admin role. Registration is controlled by `NUROLI_REGISTRATION_OPEN` (default true). No admin settings screen or instance-settings table in v1. | confirmed | Operator configuration already exists; an admin UI would be the role's only use. |
| R-15 | No email verification in v1. Password recovery is the operator command `nuroli reset-password <email>` inside the API container, which sets a temporary password and revokes sessions. SMTP flows are deferred. | confirmed | Local installs have no mail server. |
| R-16 | One sign-in method per email. Google sign-in for an email already registered by password is rejected with a clear message, and vice versa. Linking is deferred. | confirmed | Removes the pre-registration account-takeover path without an extra flow. |
| R-17 | Knowledge answers are search-gated. No matching confirmed summaries: the API ends the stream with `insufficient_evidence` and no model call. Matches: the model answers only from the supplied summaries, cites them by marker, and states gaps in prose. Web content is never mixed into a knowledge answer. | confirmed | Retrieval decides evidence, not the model. |
| R-18 | A summary version has a plain-text title, one Markdown body edited in a single field with suggested headings, and a read-only source list copied from the conversation's assistant messages when the draft is generated. | confirmed | Fast to edit, easy to generate from a chat-only model, citations cannot be invented by hand. |
| R-19 | Compose topology: `web` (nginx serving the React build and proxying `/api`), `api` (FastAPI, runs migrations on start), `db` (PostgreSQL 18 on a named volume). Only the web port is published. The API service gets a host-gateway entry so host-local model runtimes are reachable at `host.docker.internal`. | confirmed | One origin for cookies; static caching and body limits in nginx; Python image stays Python-only. |
| R-20 | Stop keeps partial assistant text, marks the message stopped, and keeps it in later context with a marker. A failed reply is stored with state failed and its error code, excluded from model context; retry appends a new assistant message; superseded failed messages are hidden in the UI. Assistant messages are never edited in place. | confirmed | Append-only history keeps the invariant simple and the record honest. |
| R-21 | Operator-configurable limits with defaults: 1 concurrent stream per user; 60 replies per user per hour; 30 searches per user per hour; 2048 output tokens per reply; 24,000-character context budget dropping oldest messages first; 64 KB request body; model timeout 120 s total and 30 s to first token. Enforced server-side. | confirmed | Bounds cost and abuse without a billing system. |
| R-22 | "Herdr" means the open-source Rust terminal multiplexer (motionharvest/herdr), not the herdr.org SaaS platform. | confirmed | Only the multiplexer runs coding agents locally. |
| R-23 | DESIGN.html is a written design specification with static HTML/CSS mockups and the token set carried over from the earlier prototype. No simulated behavior. | confirmed | A specification must reflect decisions exactly. |
| R-24 | API conventions: all endpoints under `/api/v1`; JSON error envelope with stable machine code, message, and optional details; UUIDv7 identifiers generated in the application; UTC ISO 8601 timestamps; cursor pagination on created time plus id. | confirmed | One versioned contract serves web and a future mobile client. |
| R-25 | Toolchain. Backend: Python 3.14 (R-28), uv, Ruff, Pyright, pytest, SQLAlchemy 2 async, Alembic, pydantic-settings, httpx, argon2-cffi, Authlib. Frontend: pnpm, Vite, React 19, strict TypeScript, React Router, TanStack Query, plain CSS with design tokens, ESLint and Prettier, Vitest with Testing Library, Playwright, react-markdown with rehype-sanitize. | confirmed | Widely known tools that weaker implementation models handle reliably. |
| R-26 | Development workflow: OpenCode project agents with an implementer (edit allowed inside its worktree) and a reviewer (edit denied, tests allowed, different model from the implementer); OpenRouter as an optional gateway with data collection denied and model ids kept out of the repository; Herdr as an optional pane and worktree convenience with no socket-API automation; at most two concurrent implementers plus one reviewer. Process lives in AGENTS.md, IMPLEMENTATION.md, repository commands, and pull requests. | confirmed | Every tool is swappable; enforcement comes from permissions and repository gates. |
| R-27 | Skills and practices catalog (section 22.3) adopted: no third-party skill packages required; AGENTS.md entry point; ASVS 5.0 and WCAG 2.2 AA as acceptance sources; test-first for domain and use cases; tool-enforced boundaries; adapter contract tests with recorded fixtures. Omitted: Anthropic frontend-design and webapp-testing skills, spec-kit and BMAD style frameworks. | confirmed | Each adopted item improves delivery; each omitted item mainly adds tokens. |
| R-28 | Python 3.14 for native `uuid.uuid7()`. | confirmed | One dependency fewer; all listed libraries ship 3.14 wheels. |
| R-29 | Quality gates: pre-commit framework running Ruff, Prettier, ESLint, gitleaks; CI running Pyright, tests, `alembic check`, pip-audit, pnpm audit; Trivy image scan on release; axe-core in Playwright. Dependency updates through `make deps-update` run by the owner (amended by R-40; Dependabot removed). | confirmed | Secrets, vulnerabilities, drift, and accessibility caught before merge or release. |
| R-30 | Conversation title is the first user message truncated to 80 characters; editable; no title-generation model call. | confirmed | Avoids a model call per conversation; users rename when it matters. |
| R-31 | One summary per conversation; regenerating a draft overwrites the existing draft. | confirmed | Keeps the conversation-to-knowledge link one-to-one and the state machine small. |
| R-32 | Deleting a conversation deletes its messages; a confirmed summary survives with its conversation link cleared and shows "source conversation deleted"; a draft-only summary is deleted with it. | confirmed | Knowledge the user confirmed outlives its working material. |
| R-33 | Knowledge answers are streamed and not stored. | confirmed | No history feature is needed for the loop; avoids a table and a screen. |
| R-34 | Passwords are 12 to 128 characters with no composition rules. | confirmed | Length is the strongest simple rule and matches current OWASP guidance. |
| R-35 | Sessions expire after 30 days idle (sliding) and 90 days absolute. | confirmed | Bounded exposure of a stolen cookie without frequent re-login on a personal install. |
| R-36 | Login throttling: 10 failed attempts per email and per client address per 15 minutes returns 429. | confirmed | Blunts online guessing with an in-memory counter and no extra service. |
| R-37 | An assistant message still in state streaming five minutes after creation is reported as failed on read, and marked failed at API start. | confirmed | Recovers honestly from a crashed stream without a background worker. |
| R-38 | Markdown rendering allows no raw HTML; links must be http or https and open with rel="noopener noreferrer nofollow"; images disabled. | confirmed | Closes script and phishing vectors from model and web text. |
| R-39 | A knowledge answer uses the top 5 ranked summaries, truncated to the context budget. | confirmed | Enough evidence for a focused answer within the character budget. |
| R-40 | Every commit in the repository is authored and committed under the repository owner's git identity. No co-author or sign-off trailers, no bot commits, no agent identities. Pull requests are merged by the owner with a local fast-forward after rebase; the GitHub merge button is not used. Dependency updates come from `make deps-update` instead of Dependabot. | confirmed | The owner is accountable for every change in the history; bots and agents leave no separate authorship. |

---

## 4. Domain model (DDD-lite)

### 4.1 Approach

Three domain modules, each with `domain`, `application`, `infrastructure`, and
`api` packages. Domain code is plain Python (dataclasses, enums, functions)
with no imports from FastAPI, SQLAlchemy, Pydantic, httpx, or any provider SDK.
Application code orchestrates use cases through port protocols. Infrastructure
implements the ports. The API layer translates HTTP to use-case calls.

Deliberate simplifications, recorded so nobody "fixes" them later:

- No domain event bus. The only cross-aggregate effect (indexing on confirm)
  happens inside the same transaction in the same module.
- No generic repository. Each repository protocol lists only the methods its
  use cases need.
- No separate read models. List endpoints query the same tables with explicit
  columns.
- No CQRS, no sagas, no worker processes or queues. Streaming runs inside the
  request. Two in-process timers run in the API lifespan: hourly session purge
  and stale-stream reconciliation (R-37). They are the only background code.
- A shared kernel holds only ids, the `Source` value object, and error types.
- Shared ports (`ChatModelPort`, `WebSearchPort`) live in a neutral `ports`
  package so no module imports another module to reach a port.

### 4.2 Bounded contexts and modules

| Module | Owns | Uses ports | Exposes use cases |
| --- | --- | --- | --- |
| `identity` | User aggregate, credentials, Google identity, sessions, registration policy | Password hasher, Google OAuth client, clock | Register, Login, StartGoogleSignIn, CompleteGoogleSignIn, Logout, GetCurrentUser, ChangePassword, ResetPasswordByOperator |
| `conversations` | Conversation aggregate, messages, context assembly, research attachment | ChatModelPort, WebSearchPort, clock | CreateConversation, ListConversations, GetConversation, RenameConversation, DeleteConversation, SendMessage (streaming), RetryReply (streaming) |
| `knowledge` | Summary aggregate, versions, archive, retrieval, knowledge answers | ChatModelPort, clock | GenerateDraft, GetSummary, UpdateDraft, ConfirmSummary, DiscardDraft, ArchiveSummary, UnarchiveSummary, ListSummaries, GetVersion, AskKnowledge (streaming) |
| `platform` | Settings, database engine and session, migrations, health, logging, rate limiting, operator commands | — | — |
| `shared_kernel` | `UserId`, `ConversationId`, `MessageId`, `SummaryId`, `Source`, domain error base classes | — | — |
| `ports` | `ChatModelPort`, `WebSearchPort` and their request and event types | — | — |
| `adapters` | `OpenAICompatibleChatModel`, `TavilyWebSearch`, `FakeChatModel`, `FakeWebSearch`, `Argon2PasswordHasher`, `GoogleOAuthAdapter` | — | — |

Cross-module rule: code in module A's `application` or `infrastructure` may
import module B's `application` package (its port protocols and use cases),
`shared_kernel`, and `ports`. Nothing imports another module's `domain`,
`infrastructure`, or `api`. Wiring of concrete adapters and repositories into
use cases happens in one composition root, `platform/wiring.py`, used by the
FastAPI dependencies.
Knowledge reads conversation transcripts through a small read port
(`ConversationTranscriptPort`) implemented in the conversations module, so the
Knowledge domain never depends on the Conversation aggregate.

### 4.3 Aggregates, entities, value objects, invariants

#### User (identity)

| Element | Type | Fields |
| --- | --- | --- |
| User | aggregate root | `id`, `email` (Email VO), `display_name`, `role` (admin, member), `is_active`, `password_hash` or `google_subject`, `created_at` |
| Email | value object | normalized lowercase, RFC-shaped, max 254 chars |
| PasswordHash | value object | Argon2id encoded string; never compared outside the hasher port |

Invariants: email unique per installation; exactly one credential type (R-16);
first user created is admin (R-14); inactive users cannot sign in; display name
1 to 80 characters.

Sessions are not part of the aggregate. `Session` is an infrastructure record:
`id`, `token_hash`, `user_id`, `created_at`, `expires_at`, `last_seen_at`,
`revoked_at`.

#### Conversation (conversations)

| Element | Type | Fields |
| --- | --- | --- |
| Conversation | aggregate root | `id`, `owner_id`, `title`, `created_at`, `updated_at`, `messages` |
| Message | entity | `id`, `sequence`, `role` (user, assistant), `content`, `created_at`, plus role-specific fields below |
| user message | | `research_requested: bool` |
| assistant message | | `model_name`, `state` (streaming, complete, stopped, failed), `error_code`, `research_query`, `sources: list[Source]`, `prompt_tokens`, `completion_tokens`, `completed_at`, `replies_to: MessageId` |
| Source | value object (shared kernel) | `title`, `url` (https only, max 2048), `publisher` (host), `snippet` (max 500 chars) |

Invariants: owner fixed at creation; sequence strictly increasing and
append-only; an assistant message always references the user message it
answers; sources only on assistant messages; state transitions only
`streaming -> complete | stopped | failed`; content of a user message 1 to
32,000 characters; at most one assistant message in state `streaming` per
conversation.

#### Summary (knowledge)

| Element | Type | Fields |
| --- | --- | --- |
| Summary | aggregate root | `id`, `owner_id`, `conversation_id` (nullable after R-32), `state` (draft, confirmed, archived), `draft` (nullable Draft VO), `versions`, `created_at`, `updated_at` |
| Draft | value object | `title`, `body_markdown`, `sources`, `generated_by_model` (nullable), `revision` (int), `updated_at` |
| SummaryVersion | entity | `id`, `version_number`, `title`, `body_markdown`, `sources`, `generated_by_model`, `created_at` |

Invariants: owner equals the source conversation owner at creation; state
`draft` means no versions and a draft present; `confirmed` means at least one
version; `archived` means at least one version and excluded from retrieval;
confirming requires a draft and produces exactly one new version with number
`max + 1`; confirmed versions are immutable; editing after confirmation creates
a draft from the current version; one summary per conversation (R-31); title 1
to 200 characters; body 1 to 50,000 characters; sources on a version are copied
from the draft and cannot be edited by the user.

State machine:

```
(none) --GenerateDraft--> draft --Confirm--> confirmed
draft --DiscardDraft--> (deleted)
confirmed --GenerateDraft / StartEdit--> confirmed with draft --Confirm--> confirmed (new version)
confirmed with draft --DiscardDraft--> confirmed
confirmed --Archive--> archived --Unarchive--> confirmed
```

### 4.4 Domain services (pure functions or classes without I/O)

| Service | Module | Responsibility |
| --- | --- | --- |
| `ContextAssembler` | conversations | Selects messages within the character budget (newest first, whole messages), excludes failed messages, renders stopped messages with a `[reply stopped by user]` marker, prepends the system prompt, appends the research block when sources exist |
| `ResearchQueryPrompt` | conversations | Builds the bounded prompt that asks the model for a single search query from the recent context |
| `SourceSanitizer` | shared kernel | Validates URL scheme and length, truncates snippets, derives publisher from host |
| `SummaryPrompt` | knowledge | Builds the transcript-to-summary prompt requesting title and Markdown body |
| `KnowledgeAnswerPrompt` | knowledge | Builds the answer prompt with numbered summaries and the instruction to cite markers and state gaps |
| `PasswordPolicy` | identity | Length rules (R-34) |
| `RegistrationPolicy` | identity | Combines the registration flag and the "first user is admin" rule |

### 4.5 Ports (application layer protocols)

`ChatModelPort` and `WebSearchPort` are defined in `nuroli/ports/`. Module-
specific ports (`PasswordHasherPort`, `GoogleOAuthPort`,
`ConversationTranscriptPort`) are defined by the module that consumes them in
its `application/ports.py`.

```python
class ChatModelPort(Protocol):
    async def complete(self, request: ChatRequest) -> ChatCompletion: ...
    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]: ...
    # ChatEvent = Delta(text) | Done(usage, finish_reason) | Failure(code, message, retryable)

class WebSearchPort(Protocol):
    @property
    def enabled(self) -> bool: ...
    async def search(self, query: str, max_results: int) -> list[Source]: ...

class PasswordHasherPort(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, encoded: str) -> bool: ...

class GoogleOAuthPort(Protocol):
    def authorization_url(self, state: str, code_verifier: str) -> str: ...
    async def exchange_code(self, code: str, code_verifier: str) -> GoogleIdentity: ...
    # GoogleIdentity = subject, email, email_verified, name

class ConversationTranscriptPort(Protocol):
    async def get_transcript(self, conversation_id, owner_id) -> Transcript | None: ...
    # Transcript = title, messages (role, content, sources), for summary generation only
```

### 4.6 Repository interfaces

```python
class UserRepository(Protocol):
    async def get(self, user_id) -> User | None
    async def get_by_email(self, email) -> User | None
    async def get_by_google_subject(self, subject) -> User | None
    async def count(self) -> int
    async def add(self, user) -> None
    async def save(self, user) -> None

class SessionRepository(Protocol):
    async def create(self, user_id, token_hash, expires_at) -> None
    async def get_active(self, token_hash, now) -> Session | None
    async def touch(self, session_id, now) -> None
    async def revoke(self, session_id) -> None
    async def revoke_all_for_user(self, user_id) -> None
    async def purge_expired(self, now) -> int

class ConversationRepository(Protocol):
    async def add(self, conversation) -> None
    async def get_owned(self, conversation_id, owner_id) -> Conversation | None
    async def list_owned(self, owner_id, cursor, limit) -> Page[ConversationListItem]
    async def save(self, conversation) -> None      # persists new messages and changed assistant messages
    async def delete(self, conversation_id, owner_id) -> bool

class SummaryRepository(Protocol):
    async def add(self, summary) -> None
    async def get_owned(self, summary_id, owner_id) -> Summary | None
    async def get_by_conversation(self, conversation_id, owner_id) -> Summary | None
    async def list_owned(self, owner_id, state, query, cursor, limit) -> Page[SummaryListItem]
    async def search_confirmed(self, owner_id, query, limit) -> list[RankedSummary]   # R-05 extension point
    async def save(self, summary) -> None           # updates search vector when the current version changes
    async def delete(self, summary_id, owner_id) -> bool
```

Unit of work: one SQLAlchemy `AsyncSession` per request, opened by a FastAPI
dependency. A use case commits at its end. Streaming use cases commit twice: after
creating the user and assistant message rows (so the stream can begin), and after
finalizing the assistant message. Transactions never span two aggregates except
the confirm transaction, which updates one Summary row and its own index column.

### 4.7 Layer responsibilities

| Layer | Contains | Decides | Must not |
| --- | --- | --- | --- |
| Domain | Aggregates, entities, value objects, invariants, domain services, domain errors | Whether a state change is legal; how context is assembled; what a valid source is | Import frameworks, perform I/O, know about HTTP or SQL |
| Application | Use cases, port protocols, repository protocols, DTOs returned to the API | Order of operations, transaction boundaries, which port to call, limit checks | Contain business rules that belong on an aggregate; format HTTP responses |
| Infrastructure | SQLAlchemy models and mappers, repository implementations, OpenAI-compatible adapter, Tavily adapter, Argon2 hasher, Authlib Google client, rate limiter, settings loader | How to talk to PostgreSQL and external hosts; retries and timeouts | Enforce ownership on its own; change domain state outside the aggregate |
| API (interface) | FastAPI routers, Pydantic request and response schemas, dependencies (`current_user`, `unit_of_work`), SSE encoder, error mapping | Status codes, cookie attributes, CSRF checks, schema validation | Call repositories directly; hold business rules |

Translation boundaries: Pydantic schemas map to use-case input DTOs in the API
layer. Use cases return domain objects or plain DTOs; the API layer maps them to
response schemas. Infrastructure mappers translate between SQLAlchemy rows and
domain objects in both directions. Domain objects never cross the HTTP boundary
unmapped.

### 4.8 Use-case catalogue with rules

| Use case | Inputs | Rules enforced | Output |
| --- | --- | --- | --- |
| Register | email, password, display name | registration open or first user; password policy; email unique; first user admin | user, new session token |
| Login | email, password | constant-time verify; throttle (R-36); inactive rejected | user, new session token |
| StartGoogleSignIn | — | state and PKCE verifier generated and stored in a signed short-lived cookie | redirect URL |
| CompleteGoogleSignIn | code, state | state matches; `email_verified` true; subject known -> login; unknown subject with unused email -> register if open; email used by password account -> `email_uses_password` | user, session token |
| Logout | session | revoke row | — |
| ChangePassword | current, new | verify current; policy; revoke other sessions | — |
| ResetPasswordByOperator | email | operator command only; sets temporary password; revokes sessions | temporary password printed once |
| CreateConversation | — | owner from session | conversation |
| SendMessage | conversation id, content, research flag | ownership; no stream in progress; rate limits; content length; research only if enabled | SSE stream |
| RetryReply | conversation id, user message id | ownership; the latest reply to that message is failed or stopped | SSE stream |
| DeleteConversation | conversation id | ownership; R-32 | — |
| GenerateDraft | conversation id | ownership; transcript has at least one complete assistant message; R-31 | summary with draft |
| UpdateDraft | summary id, title, body, revision | ownership; draft exists; revision matches | summary |
| ConfirmSummary | summary id, revision | ownership; draft exists; revision matches; creates version; updates index | summary |
| DiscardDraft | summary id | ownership; draft exists | summary or deleted |
| Archive / Unarchive | summary id | ownership; state rules | summary |
| AskKnowledge | question | rate limit; search owner's confirmed summaries; gate on results (R-17) | SSE stream |

---

## 5. Frontend and backend relationship

### 5.1 React application responsibilities

- Render every screen in DESIGN.html and manage navigation with React Router.
- Hold server state in TanStack Query: current user, conversation list, one
  conversation, summary list, one summary, capabilities.
- Hold local UI state only: composer text per conversation (localStorage,
  cleared on send), streaming buffer, summary editor text before it is saved
  through the draft endpoint (debounced 800 ms), open drawers and dialogs.
- Parse the SSE stream, append deltas, render sources, and finalize state.
- Abort the fetch when the user presses stop.
- Render Markdown safely (R-38) and never inject HTML from any server text.
- Send the CSRF header on every state-changing request and rely on the cookie
  for identity.
- Show the error envelope's message and offer retry when `retryable` is true.

The React application never: stores tokens or keys, decides ownership, decides
whether a summary is confirmed, or contacts the model or search provider.

### 5.2 FastAPI application responsibilities

- Authenticate every request under `/api/v1` except the public auth endpoints
  and health endpoints.
- Enforce CSRF, rate limits, body limits, and ownership.
- Execute use cases inside one transaction per request.
- Call the model and search provider with server-held credentials.
- Stream replies and finalize message state even when the client disconnects.
- Run migrations on start, expose health and readiness, and provide operator
  commands.

### 5.3 Never trusted from the browser

User ids, owner ids, roles, model names, source URLs, summary state, confirmation
flags, timestamps, token counts, and any "admin" indication. All are derived or
validated on the server.

### 5.4 Same API for a future mobile client

The API is JSON over HTTPS under `/api/v1` with SSE streaming. A mobile client
would authenticate with the same login endpoints and receive the session token in
the response body when it sends `Accept: application/vnd.nuroli.token` (future
variant), then use `Authorization: Bearer` against the same sessions table. No
endpoint depends on browser-only behavior other than the cookie transport.

---

## 6. API endpoint inventory

All paths are prefixed with `/api/v1`. All responses are JSON unless marked SSE.
"Auth" means a valid session is required. "Owner" means the record must belong
to the session user or the response is 404.

Error envelope:

```json
{ "error": { "code": "registration_closed", "message": "Registration is closed on this installation.", "details": null, "retryable": false } }
```

Stable codes: `validation_failed` (422, `details.fields`), `unauthenticated`
(401), `csrf_rejected` (403), `registration_closed` (403), `email_taken` (409),
`email_uses_google` (409), `email_uses_password` (409), `invalid_credentials`
(401), `rate_limited` (429, `details.retry_after_seconds`), `not_found` (404),
`stream_in_progress` (409), `draft_stale` (409), `no_draft` (409),
`invalid_state` (409), `research_unavailable` (409), `model_unavailable`
(502), `model_timeout` (504), `model_error` (502), `payload_too_large` (413),
`internal_error` (500), `password_change_required` (403, returned for every
authenticated endpoint except password change, me, and logout while the
`must_change_password` flag is set), `server_shutdown` (stored as the error code
of a reply interrupted by an API shutdown; never returned over HTTP).

### 6.1 Public and session

| Method and path | Auth | Request | Success | Errors |
| --- | --- | --- | --- | --- |
| `GET /auth/options` | none | — | `{registration_open, google_enabled}` | — |
| `POST /auth/register` | none | `{email, password, display_name}` | 201 `{user}` + session cookie | 403 registration_closed, 409 email_taken, 409 email_uses_google, 422 |
| `POST /auth/login` | none | `{email, password}` | 200 `{user}` + cookie | 401 invalid_credentials, 429 |
| `GET /auth/google/start` | none | — | 302 to Google, sets signed state cookie | 409 if Google not configured |
| `GET /auth/google/callback` | none | `code`, `state` | 302 to `/` with cookie | 302 to `/login?error=<code>` for state_mismatch, email_unverified, registration_closed, email_uses_password |
| `POST /auth/logout` | auth | — | 204, cookie cleared | — |
| `GET /auth/me` | auth | — | `{user: {id, email, display_name, role, created_at}}` | 401 |
| `POST /auth/password` | auth | `{current_password, new_password}` | 204 | 401 invalid_credentials, 422 |
| `PATCH /auth/me` | auth | `{display_name}` | 200 `{user}` | 422 |
| `GET /system/capabilities` | auth | — | `{model_name, research_enabled, limits: {max_message_chars, output_tokens}}` | — |
| `GET /health` (no prefix) | none | — | `{status: "ok"}` | — |
| `GET /ready` (no prefix) | none | — | `{status: "ok", database: "ok", migrations: "current"}` | 503 |

### 6.2 Conversations

| Method and path | Auth | Request | Success | Errors |
| --- | --- | --- | --- | --- |
| `GET /conversations?cursor&limit` | auth | limit 1 to 50, default 20 | `{items: [{id, title, updated_at, summary_state}], next_cursor}` | 422 |
| `POST /conversations` | auth | `{}` | 201 `{conversation}` | — |
| `GET /conversations/{id}` | owner | — | `{id, title, created_at, updated_at, messages: [...]}` (superseded failed replies included with `superseded: true`) | 404 |
| `PATCH /conversations/{id}` | owner | `{title}` | 200 `{conversation}` | 404, 422 |
| `DELETE /conversations/{id}` | owner | — | 204 | 404, 409 stream_in_progress |
| `POST /conversations/{id}/messages` | owner | `{content, research: bool}` | 200 SSE (section 7) | 404, 409 stream_in_progress, 409 research_unavailable, 413, 422, 429 |
| `POST /conversations/{id}/messages/{user_message_id}/retry` | owner | `{}` | 200 SSE | 404, 409 invalid_state, 409 stream_in_progress, 429 |

Message schema in responses: `{id, sequence, role, content, created_at,
research_requested?, model_name?, state?, error_code?, research_query?,
sources?, replies_to?, superseded?}`. Token counts are not returned in v1.

### 6.3 Summaries and knowledge

| Method and path | Auth | Request | Success | Errors |
| --- | --- | --- | --- | --- |
| `POST /conversations/{id}/summary/draft` | owner | `{}` | 200 `{summary}` (synchronous, up to model timeout) | 404, 409 invalid_state (no complete reply), 409 stream_in_progress, 429, 502, 504 |
| `GET /summaries?state=confirmed|archived&q&cursor&limit` | auth | `state` defaults to `confirmed` | `{items: [{id, title, state, conversation_id, updated_at, version_number, preview}], next_cursor}` | 422 |
| `GET /summaries/{id}` | owner | — | `{id, state, conversation_id, conversation_deleted, draft: {...} or null, current_version: {...} or null, versions: [{version_number, created_at}]}` | 404 |
| `GET /summaries/{id}/versions/{n}` | owner | — | `{version}` | 404 |
| `PATCH /summaries/{id}/draft` | owner | `{title, body_markdown, revision}` | 200 `{summary}` | 404, 409 no_draft, 409 draft_stale, 422 |
| `POST /summaries/{id}/confirm` | owner | `{revision}` | 200 `{summary}` | 404, 409 no_draft, 409 draft_stale |
| `DELETE /summaries/{id}/draft` | owner | — | 200 `{summary}` or 204 when the summary is deleted | 404, 409 no_draft |
| `POST /summaries/{id}/archive` | owner | — | 200 `{summary}` | 404, 409 invalid_state |
| `POST /summaries/{id}/unarchive` | owner | — | 200 `{summary}` | 404, 409 invalid_state |
| `POST /knowledge/ask` | auth | `{question}` (1 to 2,000 chars) | 200 SSE (section 7.3) | 409 stream_in_progress, 413, 422, 429 |

---

## 7. Streaming contract

### 7.1 Transport

`POST` with a JSON body; response `Content-Type: text/event-stream`,
`Cache-Control: no-cache`, `X-Accel-Buffering: no` (nginx). The server writes a
comment line `: ping` every 15 seconds while idle. Errors detected before the
first event use the JSON envelope with a normal status code; errors after the
stream starts use the `error` event and the stream ends.

### 7.2 Reply stream (SendMessage, RetryReply)

```
event: start
data: {"conversation_id":"…","user_message_id":"…","assistant_message_id":"…","model_name":"…"}

event: research            (only when research was requested)
data: {"status":"searching","query":"…"}
data: {"status":"done","result_count":5}
data: {"status":"skipped","reason":"not_configured"|"rate_limited"|"failed"}

event: sources             (only when results exist)
data: {"sources":[{"title":"…","url":"https://…","publisher":"…","snippet":"…"}]}

event: delta
data: {"text":"…"}

event: end
data: {"state":"complete"|"stopped","finish_reason":"stop"|"length"}

event: error
data: {"code":"model_unavailable"|"model_timeout"|"model_error"|"context_too_long","message":"…","retryable":true}
```

Lifecycle on the server:

1. Validate, check limits, create the user message and an assistant message in
   state `streaming`, commit, emit `start`.
2. If research is on and enabled: emit `research searching`, call `complete`
   for the query, call `search`, sanitize, emit `sources`; on any failure emit
   `research skipped` and continue without sources.
3. Stream deltas from the adapter, buffering content in memory.
4. On adapter completion: persist content and usage, state `complete`, emit
   `end`.
5. On client disconnect: persist buffered content, state `stopped`, no further
   events. Detected through `request.is_disconnected()` between chunks.
6. On adapter failure or timeout: persist any content with state `failed` and
   the error code, emit `error`.
7. Release the per-user concurrency slot in a `finally` block.

### 7.3 Knowledge answer stream (AskKnowledge)

```
event: start
data: {"model_name":"…"}

event: citations
data: {"citations":[{"marker":1,"summary_id":"…","title":"…","conversation_id":"…"}]}

event: delta
data: {"text":"…"}

event: end
data: {"outcome":"answered"|"insufficient_evidence"}

event: error
data: {...}
```

With no matching summaries the server emits `start`, `citations` with an empty
list, and `end` with `insufficient_evidence`, without calling the model.

### 7.4 Client rules

Parse `event:` and `data:` lines; ignore comments; treat a closed stream without
`end` or `error` as a network failure and show retry. The client aborts the
request to stop. After any terminal event, refetch the conversation so the
persisted state is the source of truth.

---

## 8. Authentication, registration, sessions, and recovery

- **Password storage.** Argon2id through argon2-cffi with the library defaults
  reviewed against the OWASP Password Storage Cheat Sheet (memory 19 MiB or
  more, iterations 2 or more, parallelism 1). Rehash on login when parameters
  change.
- **Registration.** Allowed when `NUROLI_REGISTRATION_OPEN=true` or when no user
  exists. The first user becomes admin. Responses never reveal whether an email
  exists beyond the documented `email_taken` conflict, which is acceptable for a
  self-hosted installation where registration is either open or closed.
- **Login throttling.** In-memory counters keyed by normalized email and by
  client address (R-36). The API trusts `X-Forwarded-For` only from the `web`
  container's address.
- **Google sign-in.** Authorization code flow with PKCE and a random state,
  both stored in a signed, HttpOnly, 10-minute cookie. The callback validates
  state, exchanges the code server-side, verifies the ID token signature,
  issuer, audience, and expiry through Authlib, requires `email_verified`, and
  then applies R-16. Redirect URI is `${NUROLI_PUBLIC_ORIGIN}/api/v1/auth/google/callback`
  and must be registered in Google Cloud Console by the operator.
- **Sessions.** 32-byte random token, SHA-256 hash stored; cookie
  `nuroli_session`, HttpOnly, Secure, SameSite=Lax, Path=/. Sliding expiry
  (R-35) updated at most once per five minutes. Logout and password change
  revoke. Expired rows are purged by an hourly in-process timer in the API
  lifespan (section 4.1).
- **Recovery.** `nuroli reset-password <email>` prints a temporary password
  once, marks the account `must_change_password` , and
  revokes sessions. The user is prompted to change it on next login.
- **Plain HTTP installs.** `NUROLI_SESSION_COOKIE_SECURE` defaults to true.
  Browsers accept Secure cookies on `localhost`. An operator exposing the app
  over plain HTTP on a LAN address must set it to false and accept the risk,
  which the installation section of DESIGN.html states plainly.

---

## 9. Authorization and ownership enforcement

- A single FastAPI dependency `current_user` resolves the session or raises
  401. Routers under `/api/v1` include it by default; public endpoints opt out
  explicitly.
- Every repository read of a Conversation or Summary takes `owner_id` and
  filters in SQL. Use cases never load by id alone.
- Missing and foreign records both produce `not_found`.
- Knowledge retrieval filters by `owner_id` and `state = 'confirmed'` in the
  same query as the full-text match.
- Tests required for every owned resource: a second user receives 404 on read,
  update, delete, stream, draft, confirm, and retrieval.
- The admin role is checked nowhere in v1 and this is asserted by a test so it
  cannot silently grow authority.

---

## 10. Data model

PostgreSQL 18. Identifiers are UUIDv7 generated in the domain layer. All
timestamps are `timestamptz`.

```
users
  id uuid pk
  email citext unique not null
  display_name text not null
  role text not null check (role in ('admin','member'))
  is_active boolean not null default true
  password_hash text null
  google_subject text unique null
  must_change_password boolean not null default false
  created_at, updated_at timestamptz not null
  check ((password_hash is not null) <> (google_subject is not null))

sessions
  id uuid pk
  token_hash bytea unique not null
  user_id uuid not null references users on delete cascade
  created_at, expires_at, last_seen_at timestamptz not null
  revoked_at timestamptz null
  index (user_id), index (expires_at)

conversations
  id uuid pk
  owner_id uuid not null references users on delete cascade
  title text not null
  created_at, updated_at timestamptz not null
  index (owner_id, updated_at desc, id desc)

messages
  id uuid pk
  conversation_id uuid not null references conversations on delete cascade
  sequence integer not null
  role text not null check (role in ('user','assistant'))
  content text not null default ''
  research_requested boolean not null default false
  replies_to uuid null references messages
  model_name text null
  state text null check (state in ('streaming','complete','stopped','failed'))
  error_code text null
  research_query text null
  sources jsonb not null default '[]'
  prompt_tokens integer null, completion_tokens integer null
  created_at timestamptz not null, completed_at timestamptz null
  unique (conversation_id, sequence)

summaries
  id uuid pk
  owner_id uuid not null references users on delete cascade
  conversation_id uuid unique null references conversations on delete set null
  state text not null check (state in ('draft','confirmed','archived'))
  draft_title text null, draft_body text null, draft_sources jsonb null
  draft_generated_by text null, draft_revision integer not null default 0
  draft_updated_at timestamptz null
  current_version_number integer null
  search_vector tsvector null
  created_at, updated_at timestamptz not null
  index (owner_id, state, updated_at desc, id desc)
  gin index (search_vector)

summary_versions
  id uuid pk
  summary_id uuid not null references summaries on delete cascade
  version_number integer not null
  title text not null, body_markdown text not null
  sources jsonb not null default '[]'
  generated_by_model text null
  created_at timestamptz not null
  unique (summary_id, version_number)
```

Lifecycles:

- **Conversation.** Created empty; messages appended; title editable; deleted
  by owner (R-32) or with the user.
- **Message.** User message immutable. Assistant message mutable only in the
  `streaming` state; terminal states are final. Superseded failed replies stay
  in the table.
- **Summary.** As in section 4.3. `search_vector` is set from the current
  version's title and body on confirm and cleared on archive; unarchive
  restores it. Drafts never touch the vector.
- **Session.** Created on login; touched on use; revoked on logout or password
  change; purged after expiry.
- **User deletion.** Operator command only in v1; cascades through all tables.

Sources are stored as JSON arrays of `{title, url, publisher, snippet}` because
they are immutable value objects read with their parent and never queried.

---

## 11. Model connection

### 11.1 Configuration

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `NUROLI_MODEL_BASE_URL` | yes | — | OpenAI-compatible base URL, e.g. `https://openrouter.ai/api/v1` or `http://host.docker.internal:11434/v1` |
| `NUROLI_MODEL_NAME` | yes | — | Model identifier sent as `model` |
| `NUROLI_MODEL_API_KEY` | no | empty | Bearer token; empty for local runtimes without auth |
| `NUROLI_MODEL_TIMEOUT_SECONDS` | no | 120 | Total request timeout |
| `NUROLI_MODEL_FIRST_TOKEN_TIMEOUT_SECONDS` | no | 30 | Time to first streamed token |
| `NUROLI_MODEL_MAX_OUTPUT_TOKENS` | no | 2048 | `max_tokens` sent per request |
| `NUROLI_MODEL_EXTRA_HEADERS` | no | empty | JSON object of extra headers (OpenRouter attribution headers, for example) |

Private and loopback addresses are permitted for the model base URL because it
is trusted operator configuration (section 17). Startup validates the URL shape
and logs the host and model name, never the key.

### 11.2 Adapter boundary

`OpenAICompatibleChatModel` implements `ChatModelPort` using httpx. It sends
`POST {base_url}/chat/completions` with `messages`, `model`, `max_tokens`,
`stream`, and `temperature`; parses `data:` lines with `choices[0].delta.content`;
reads `usage` when present; maps HTTP 401/403 to `model_unavailable`, 404 to
`model_unavailable` (unknown model), 429 to `model_error` with
`retryable: true`, 5xx and connection errors to `model_unavailable`, timeouts
to `model_timeout`, and `finish_reason: length` to a normal `end` with
`finish_reason` reported. One retry with backoff for connection errors before
the first byte only; never retry after streaming has begun.

Operator command `nuroli check-model` sends a one-token request and prints the
outcome, so misconfiguration is visible before users hit it.

### 11.3 Deferred on purpose

No provider registry, no per-user keys, no capability detection, no tool
calling, no JSON mode, no embeddings, no model list endpoint, no fallback
routing. Adding a second provider later means one new adapter class, one
`NUROLI_MODEL_PROTOCOL` variable, and a factory in the platform module.
Per-reply model choice later means a `model_connections` table and a
`model_id` on the send request; the `model_name` column already exists.

### 11.4 Testing without paid calls

- Unit tests use `FakeChatModel` (application test double) that yields scripted
  deltas, failures, or delays.
- Contract tests run the real adapter against `respx` mocked responses recorded
  from a real OpenAI-compatible endpoint (fixtures checked in with no secrets)
  covering success, `length`, 401, 429, 5xx, malformed chunk, and timeout.
- An optional live test, skipped unless `NUROLI_LIVE_MODEL_TESTS=1`, sends one
  short request and is never run in CI.

---

## 12. Web research boundary

- `TavilyWebSearch` implements `WebSearchPort` with httpx against
  `NUROLI_TAVILY_BASE_URL`, `search_depth: basic`, `max_results: 5`, timeout 10 s.
  Results pass through `SourceSanitizer`: https only, length limits, publisher
  from host, duplicate URLs removed.
- `NUROLI_SEARCH_PROVIDER` is `tavily` or `none`; `none` reports
  `enabled = false`, the capabilities endpoint says research is unavailable,
  the composer hides the toggle, and a request with `research: true` returns
  `research_unavailable`.
- Snippets enter the prompt inside a delimited block labelled as untrusted web
  content with the instruction to use them as evidence only and to cite by
  number. The block never contains instructions from the pages.
- The model reply cites sources by number; the API attaches the sanitized
  source list to the assistant message regardless of which the model cited,
  and the UI renders the list under the reply. Source links come only from the
  search results, never from model text.
- Contract tests use recorded Tavily responses; unit tests use
  `FakeWebSearch`.

---

## 13. Knowledge retrieval architecture

- On confirm: `search_vector = setweight(to_tsvector('english', title), 'A') ||
  setweight(to_tsvector('english', body_markdown), 'B')` in the same UPDATE
  as the state change.
- Query: `websearch_to_tsquery('english', :q)` against `search_vector` where
  `owner_id = :owner and state = 'confirmed'`, ordered by `ts_rank_cd`, limit 5
  (R-39). Library search uses the same query restricted to the requested
  state (default `confirmed`, or `archived`) plus a title `ILIKE` fallback for
  queries shorter than three characters.
- The answer prompt lists summaries as `[1] Title` blocks with bodies truncated
  to fit the context budget, instructs the model to answer only from them, to
  cite markers, and to say what is not covered.
- No indexing job, no queue, no reindex command needed; a migration can rebuild
  vectors with one SQL statement.
- Extension: adding an `embedding vector` column and a hybrid ranking later
  touches only `search_confirmed` and one migration.

---

## 14. Persistence design

- SQLAlchemy 2 async with asyncpg; one engine per process; `expire_on_commit=False`.
- ORM models live in each module's `infrastructure/models.py`; domain objects
  are mapped explicitly by small mapper functions. No ORM object leaves
  infrastructure.
- Alembic with one migration per ticket that changes schema, autogenerate
  reviewed by hand, `alembic check` in CI, and migrations applied by the API
  container on start under a PostgreSQL advisory lock so two starts cannot
  race.
- Integration tests run against a real PostgreSQL (Compose or CI service) on a
  per-test transaction rollback.
- `citext` extension for emails. No other extensions.
- Composition root `platform/wiring.py` builds repositories and adapters for a
  request; FastAPI dependencies call it. No module instantiates another
  module's infrastructure.

---

## 15. Docker Compose topology and local model connectivity

```
web  (nginx)      published port ${NUROLI_WEB_PORT:-8080}
  serves /            React build (immutable assets cached, index no-cache)
  proxies /api, /health, /ready -> api:8000 (proxy_buffering off for SSE, client_max_body_size 64k)
api  (uvicorn)    internal only; runs `alembic upgrade head` then serves; one worker process
  extra_hosts: host.docker.internal:host-gateway
  env_file: .env
db   (postgres:18) internal only; volume nuroli_pgdata
  healthcheck pg_isready; api depends_on db healthy
```

- Three Compose files: `compose.yaml` (release images from the registry),
  `compose.dev.yaml` (bind mounts, reload, Vite dev server with proxy, exposed
  PostgreSQL port, fake model container), and `compose.test.yaml` (release-
  shaped stack plus the fake model container, used by end-to-end tests).
- The API runs a single uvicorn worker because rate limits and concurrency
  slots are in-memory. Running replicas is deferred and would require a shared
  store for those counters.
- Every published or exposed port is a variable (`NUROLI_WEB_PORT`,
  `NUROLI_DEV_API_PORT`, `NUROLI_DEV_DB_PORT`, `NUROLI_DEV_VITE_PORT`,
  `NUROLI_DEV_FAKE_MODEL_PORT`) and the Compose project name comes from
  `COMPOSE_PROJECT_NAME`, so several worktrees can run stacks side by side
  (IMPLEMENTATION.md section 4.3).
- Local model runtime on the host: set the base URL to
  `http://host.docker.internal:<port>/v1`. Runtime in another container on the
  same Compose network: use its service name. Remote HTTPS: the URL as given.
- Remote access is the operator's responsibility through an HTTPS reverse proxy
  in front of `web`; the API trusts forwarded headers only from `web`.
- Images are built by CI, tagged with the release version and digest, and
  published to GitHub Container Registry as `ghcr.io/amirhosseinsaloot/nuroli-api`
  and `ghcr.io/amirhosseinsaloot/nuroli-web`. No image contains secrets or `.env`.

---

## 16. Configuration and secrets

- Single `.env` file read by Compose and by pydantic-settings with the
  `NUROLI_` prefix. `.env.example` ships with placeholders only.
- Required at start: `NUROLI_PUBLIC_ORIGIN`, `NUROLI_SECRET_KEY` (32+ random
  bytes, signs the OAuth state cookie), `NUROLI_DATABASE_URL`,
  `POSTGRES_PASSWORD`, `NUROLI_MODEL_BASE_URL`, `NUROLI_MODEL_NAME`.
- Optional: `NUROLI_MODEL_API_KEY`, `NUROLI_SEARCH_PROVIDER`,
  `NUROLI_TAVILY_API_KEY`, `NUROLI_GOOGLE_CLIENT_ID`,
  `NUROLI_GOOGLE_CLIENT_SECRET`, `NUROLI_REGISTRATION_OPEN`,
  `NUROLI_SESSION_TTL_DAYS`, `NUROLI_SESSION_COOKIE_SECURE`, the limit
  variables from R-21, `NUROLI_LOG_LEVEL`, `NUROLI_LOG_FORMAT`,
  `NUROLI_TRUSTED_PROXY_CIDR` (peers whose `X-Forwarded-For` is honoured;
  default the Compose network), `NUROLI_TAVILY_BASE_URL` (default
  `https://api.tavily.com`; end-to-end tests point it at the fake container).
- Startup fails fast with a readable list of missing or invalid variables.
- Secrets never appear in logs, error messages, the capabilities endpoint, or
  the frontend build. `.gitignore` (Phase 3) excludes `.env*` except
  `.env.example`, key and certificate files, database dumps, `backups/`, logs,
  and agent scratch directories.
- Development, CI, and production use different values; CI uses throwaway
  values and no live provider keys.

---

## 17. Security controls

| Area | Control |
| --- | --- |
| Authentication | Argon2id; constant-time compare; throttling; Google PKCE, state, ID token verification, `email_verified` required; R-16 |
| Session | Opaque hashed tokens; HttpOnly Secure SameSite=Lax; revocation; sliding and absolute expiry |
| CSRF | Origin must equal `NUROLI_PUBLIC_ORIGIN` on POST, PATCH, DELETE; custom header required; no CORS allow-list (same origin only) |
| Authorization | Owner-scoped SQL for every read and write; 404 for foreign ids; tests per resource |
| Input validation | Pydantic schemas with length limits; 64 KB body limit at nginx and API; UUID parsing |
| Prompt injection | System prompt states that user text, transcripts, snippets, and summaries are data; snippets and summaries wrapped in delimited untrusted blocks; the model has no tools and cannot trigger any action; confirmation and save are user actions through separate endpoints; model output is stored as text and rendered sanitized |
| Untrusted content rendering | react-markdown with rehype-sanitize; no raw HTML; http and https links only; `rel="noopener noreferrer nofollow"`; images disabled in v1 |
| SSRF | No user-influenced URLs are fetched by the backend in v1. Only two outbound hosts exist, both from operator configuration. Documented rule for later page fetching: resolve and reject private, loopback, link-local, and metadata ranges before connecting, re-check on redirects, 5 MB and 10 s limits |
| Resource limits | R-21 limits; the per-user concurrency slot covers every model-backed operation (send, retry, draft generation, knowledge ask), so a second one returns `stream_in_progress`; draft generation and knowledge answers count toward the hourly reply limit; token counters; nginx timeouts (SSE read timeout 300 s); single API worker |
| Cost abuse | Per-user hourly reply and search caps; concurrency 1; no model calls before authentication; knowledge answers gated on retrieval |
| Credentials | Server-only; never serialized; `check-model` prints outcome not key |
| Dependencies | uv and pnpm lockfiles; pip-audit and pnpm audit in CI; weekly `make deps-update` by the owner (R-40); Trivy on release images |
| CI permissions | Read-only `GITHUB_TOKEN` by default; package write only in the release job; no production secrets in CI |
| Agent permissions | Implementers edit only their worktree; reviewers cannot edit; no agent has provider keys beyond a throwaway development key; every commit is authored and committed under the repository owner's git identity with no co-author or sign-off trailers, and merges are fast-forwarded locally by the owner |
| Logs | JSON logs with request id, user id, route, status, duration, model host, token counts; never message content, prompts, emails in full, tokens, or keys |
| Backups and deletion | `pg_dump` command and restore drill; user deletion cascades; deleting a conversation follows R-32 |
| Headers | nginx sets `Content-Security-Policy` (self only, no inline scripts), `X-Content-Type-Options`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY` |

Standards used as acceptance sources: [OWASP ASVS 5.0](https://owasp.org/www-project-application-security-verification-standard/),
[OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html),
[OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[OWASP LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html),
[Google OAuth 2.0 for web server applications](https://developers.google.com/identity/protocols/oauth2/web-server).

---

## 18. Error handling and retry behavior

- Domain errors map to 409 or 422 codes in one exception handler; unexpected
  exceptions map to `internal_error` with a request id and no stack trace.
- The frontend shows the envelope message inline near the action that failed
  and offers retry when `retryable` is true.
- Model failures never lose user input: the user message is persisted before
  the model is called, and retry reuses it.
- Draft edits are saved through the draft endpoint with the revision number;
  a stale revision returns `draft_stale` and the UI reloads the draft rather
  than overwriting it.
- Confirm is idempotent in effect: a second confirm with the same revision
  returns `no_draft` and the UI treats it as success by refetching.
- Adapter retries: one retry before first byte for connection errors; no
  retries for 4xx; search failures degrade to "research skipped".

---

## 19. Logging, observability, backups, and recovery

- Structured JSON logs to stdout (Compose captures them); `NUROLI_LOG_FORMAT=text`
  for development. Every request logs one line with request id, user id,
  method, route template, status, duration; model calls log host, model,
  duration, token counts, outcome.
- `GET /health` for liveness, `GET /ready` for database and migration state;
  Compose healthchecks use them.
- `make backup` runs `pg_dump -Fc` inside `db` into `./backups/<timestamp>.dump`;
  `make restore FILE=` restores into a stopped stack. The release checklist
  requires one restore drill per release.
- Recovery from a crashed stream: R-37 rule on read; the concurrency slot is
  released in `finally`; on process start, any `streaming` messages older than
  five minutes are marked failed by a startup task.
- Upgrade path: pull new images, `docker compose up -d`; migrations run on API
  start; rollback is the previous image tag plus a restore only if a migration
  was destructive, which the migration review rule forbids without a ticket.

---

## 20. CI/CD architecture

- GitHub Actions. Pull request workflow jobs: backend lint and format check,
  Pyright, unit and integration tests with a PostgreSQL service, `alembic
  check`, frontend lint, typecheck, unit tests, Playwright end-to-end against
  the Compose stack with a fake model container, pip-audit, pnpm audit,
  gitleaks. All required for merge.
- Release workflow on a version tag: build `api` and `web` images, Trivy scan,
  push to GHCR with the tag and digest, attach the Compose file and
  `.env.example` to the GitHub release.
- The fake model container is a tiny FastAPI app that speaks the
  OpenAI-compatible protocol with scripted answers, used by end-to-end tests
  and available for local development without a key.
- Branch protection on `rebuild/v1` and `master`: required checks, one review,
  no force push, linear history. Merges are local fast-forwards by the owner
  (R-40); the `conventions` job rejects any commit whose author or committer
  differs from the owner's identity or that carries a co-author or sign-off
  trailer.

---

## 21. Multi-agent development boundaries

- Ownership areas: `backend/src/nuroli/identity`, `.../conversations`,
  `.../knowledge`, `.../platform`, `frontend/src/features/<feature>`,
  `frontend/src/components`, `infra/`. One implementer per area per ticket.
- Serialized ownership (one ticket at a time, reviewer required): Alembic
  migrations, `pyproject.toml` and `uv.lock`, `package.json` and
  `pnpm-lock.yaml`, `shared_kernel`, port protocols, API schemas and the SSE
  contract, Compose files, `AGENTS.md`, this document.
- Every ticket is one branch in one worktree with its own Compose project name
  and port offsets; merges go through pull requests with reviewer evidence and
  are fast-forwarded locally by the owner so every commit carries the owner's
  identity (IMPLEMENTATION.md section 4.3).
- Conflict points are structural, not procedural: per-area Makefile includes,
  one workflow file per area, per-module routers registered once, per-feature
  frontend types, per-module test fakes. Two tickets in different areas share
  no file.
- Agents may not change any decision in section 3 or any contract in sections
  6, 7, 10, 11, or 16 without a new decision recorded here.
- Production secrets are never available to agents or CI. Development uses a
  throwaway key or the fake model container.

---

## 22. Extension points and practice catalog

### 22.1 Multiple providers and per-reply model choice

Add `model_connections` (id, name, protocol, base URL, key reference, enabled),
a factory returning a `ChatModelPort` per connection, and `model_id` on the
send request. The Conversation aggregate and streaming contract already carry
`model_name`. The capabilities endpoint grows a `models` list.

### 22.2 Hosted accounts, credits, and mobile

Usage is recorded per assistant message today. A hosted phase adds an
accounting table fed from those columns, a payment provider adapter, and
per-user budgets checked in the same limit dependency. Mobile adds the bearer
session variant (section 5.4) and nothing else on the server.

### 22.3 Skills and practices catalog (R-27)

| Area | Item | Verdict | Use when | Cost |
| --- | --- | --- | --- | --- |
| AI-assisted development | [AGENTS.md](https://agents.md/) | Adopt | Every ticket; the single entry file with commands and pointers to document sections | Low |
| AI-assisted development | [Agent Skills format](https://agentskills.io/home) | Adapt | Only if a project skill is ever written; none required in v1 | None now |
| AI-assisted development | Anthropic frontend-design, webapp-testing skills | Omit | DESIGN.html and Playwright commands cover the need | Avoided |
| AI-assisted development | Spec-kit, BMAD style frameworks | Omit | IMPLEMENTATION.md ticket contract already covers it | Avoided |
| Security | [OWASP ASVS 5.0](https://owasp.org/www-project-application-security-verification-standard/) selected L1/L2 plus cheat sheets | Adopt | Auth, session, access control, untrusted content tickets cite items | Low |
| UX | [WCAG 2.2 AA](https://www.w3.org/TR/WCAG22/) with axe in Playwright | Adopt | Every screen ticket | Low to moderate |
| FastAPI | [fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices) structure rules | Adapt | Module layout and schema separation only | Low |
| DDD and clean code | Module-by-context, Ruff complexity 10, Pyright strict on domain and application, import-boundary lint | Adopt | Every backend ticket | Low |
| TDD | Test-first for domain and use cases; test-alongside for adapters and UI; no mirror tests | Adapt | Every ticket with logic | Moderate tokens |
| PostgreSQL | One migration per ticket, `alembic check`, full-text search, UUIDv7 | Adopt | Every schema ticket | Low |
| Reliability | Health and readiness, JSON logs with redaction, backup and restore drill, migration lock | Adopt | Platform and release tickets | Low |
| Testing | Adapter contract tests with recorded fixtures (respx, MSW) | Adopt | Model, search, and frontend API tickets | Low |

Further sources consulted: [OpenCode agents](https://opencode.ai/docs/agents/),
[OpenCode skills](https://opencode.ai/docs/skills/),
[OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[Herdr repository](https://github.com/motionharvest/herdr),
[PostgreSQL 18 release](https://www.postgresql.org/about/news/postgresql-18-released-3142/),
[FastAPI client generation](https://fastapi.tiangolo.com/advanced/generate-clients/),
[Docker Compose networking](https://docs.docker.com/compose/how-tos/networking/).

---

## 23. Intended repository structure

Created in Phase 3; listed here so tickets can name exact paths.

```
AGENTS.md                      agent entry point: commands, rules, pointers
README.md                      install and operate
SECURITY.md                    boundaries and reporting (Phase 14)
Makefile                       includes make/*.mk; root file holds only help and includes
make/                          backend.mk, frontend.mk, infra.mk, agents.mk (per-area targets)
compose.yaml                   release topology (web, api, db)
compose.dev.yaml               development overrides (bind mounts, fake model)
compose.test.yaml              end-to-end stack (release shape plus fake model)
.env.example                   placeholders only
.github/workflows/             backend.yml, frontend.yml, e2e.yml, audit.yml, conventions.yml, release.yml
.github/pull_request_template.md
.opencode/agents/              implementer.md, reviewer.md (Phase 3)
scripts/                       restore-drill.sh, upgrade-test.sh
backend/
  pyproject.toml  uv.lock  alembic.ini
  src/nuroli/
    main.py                    app factory; includes the three module routers and platform routers once
    shared_kernel/             ids.py, source.py, errors.py
    ports/                     chat_model.py, web_search.py
    platform/                  settings.py, db.py, wiring.py, lifespan.py, logging.py, middleware.py, errors.py, security.py, ratelimit.py, sse.py, providers.py, health.py, system.py, cli.py
    identity/                  domain/ application/ infrastructure/ api/ (api/router.py, api/schemas.py, api/dependencies.py)
    conversations/             domain/ application/ infrastructure/ api/
    knowledge/                 domain/ application/ infrastructure/ api/
    adapters/                  openai_compatible.py, tavily.py, argon2_hasher.py, google_oauth.py, fakes.py
  migrations/versions/
  tests/unit/<module>/         tests and fakes.py per module
  tests/integration/  tests/contract/  tests/security/
frontend/
  package.json  pnpm-lock.yaml  vite.config.ts  tsconfig.json  playwright.config.ts
  src/
    app/                       router.tsx, providers.tsx, guards.tsx
    api/                       client.ts, sse.ts, errors.ts (shared transport only)
    features/<feature>/        api.ts, hooks.ts, types.ts, screens and components (auth, conversations, summaries, knowledge)
    components/                primitives and shared UI
    styles/tokens.css
  tests/e2e/                   Playwright specs
infra/
  nginx/nginx.conf
  docker/api.Dockerfile  web.Dockerfile  api-entrypoint.sh
  fake-model/                  OpenAI-compatible and Tavily-shaped fake server
docs/rebuild/                  the three planning files
```

---

## 24. Alternatives considered and consequences

| Decision | Alternative | Why not | Consequence accepted |
| --- | --- | --- | --- |
| Modular monolith | Services per context | No scaling or team need; more deployment surface | Single API process; concurrency limiter is in-memory until replicas are needed |
| Full-text search | pgvector embeddings | Second model capability and image | Lexical recall only; hybrid later |
| Snippets only | Page fetching | SSRF and extraction cost | Shallower research evidence |
| Per-message toggle | Model-decided search | Chat-only models | User must choose to research |
| SSE over POST | WebSocket | Extra infrastructure | No server-to-client push outside a request |
| DB sessions | JWT | Revocation | One table and one lookup per request |
| One method per email | Account linking | Takeover risk | Users pick one sign-in method |
| Env flag for registration | Admin UI | Only use of admin | Restart to change the flag |
| Operator reset command | SMTP reset | No mail server | Operator involvement for recovery |
| nginx web container | API serves static files | Origin, caching, limits | Third container |
| Synchronous draft generation | Background job | No worker | Request waits up to the model timeout |
| Pyright and ESLint | ty and Biome | Training exposure of weaker models | Slightly slower tools |

