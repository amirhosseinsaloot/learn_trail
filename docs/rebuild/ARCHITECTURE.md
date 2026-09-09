# Architecture Document

Status: **Implementation-ready v1 baseline.**

Branch: `rebuild/v1`.

## 1. Purpose and user

Nuroli supports the founder's way of learning: ask AI models questions,
investigate facts, continue a deep discussion, summarize what was learned, retain
that knowledge, and return to it later. The founder is the primary user. Other
people should be able to install their own copy using Docker Compose and connect
their own cloud or local model endpoints (D-09).

The first release must demonstrate a useful product and polished UX as part of a
professional founder portfolio. Shipping a working product at the lowest practical
cost takes priority over architectural complexity. There are two initial delivery
targets: the real local Docker Compose product and a demo page for investor
presentations (D-11). Vercel remains the founder's initial hosting preference for
the demo; its scope and hosting plan are not selected yet.

The longer-term direction includes a hosted service where users can pay or top up
their accounts and store learnings, plus a mobile client (D-12). These are future
phases. The initial architecture should preserve a practical path to them.

**Security remains a top priority** (D-08). Installation operators control their
infrastructure and model accounts. Use the earlier US$10 monthly target as the
planning ceiling for founder-operated demo infrastructure and usage unless the
founder revises it. It is not a shared budget for other people's installations or
a promised running cost for arbitrary models. Demo feasibility depends on its
selected behavior and hosting plan.

The founder has selected **FastAPI for the backend** and **React for the frontend**
(D-05). **Google sign-in and email/password** are the selected login methods
(D-10). V1 defaults are Vite/React/TypeScript, FastAPI/Python, PostgreSQL with
vector search support, and a three-service Docker Compose deployment (web, API,
database). Authentication uses server-managed HTTP-only sessions with Google OAuth
and email/password. These defaults remain replaceable behind small interfaces.

## 2. Agreed first-version capabilities

1. **Conversations:** ask questions and follow-up questions through a chat
   experience.
2. **Knowledge capture:** summarize and store conversations so useful knowledge
   can be reviewed later.
3. **Knowledge questions:** ask questions across the user's stored knowledge base.
4. **Accounts:** Google sign-in and email/password login for multiple users;
   the first account is the installation administrator.
5. **Installation and connections:** easy Docker Compose installation and
   user-configured OpenAI-compatible model connections.
6. **Investor presentation:** a public synthetic demo page alongside the local
   product; the Compose app is used for live presentations.

Future scope: paid hosted accounts and a mobile application. Their implementation
is not a first-release requirement.

The founder currently consults several models and asks for verified facts.
Chat will search the web when needed and show clickable sources (decision D-01).
The user can choose the model for each reply within one shared conversation
(decision D-02). A generated summary enters saved knowledge only after the user
reviews or edits it and confirms saving (decision D-03). Knowledge questions
search confirmed summaries only; full conversations remain available to reopen
(decision D-04). Model connections are configured by installation operators;
initial supported protocols/adapters and model capabilities have not been selected.

## 3. Design and implementation agreement

- Define technology, architecture, and user flows from this new product brief.
  The old application's design is not a requirement.
- The founder makes decisions; the implementation system handles the technical
  work, integration, and verification within the agreed design.
- Reuse previous projects wherever suitable. Working interpretation: reuse
  compatible code, components, and setup after evaluating them against this
  design. Reuse must not silently decide the architecture or product behavior.
- Discuss one major decision at a time. Record the selected option and rationale
  here before turning it into implementation instructions.
- Build a new development setup with a reproducible harness, proper CI/CD, and
  workflows for multiple implementation agents (D-06). Keep it usable without
  installed skills or a particular AI product. Keep complexity proportionate to
  the portfolio release.
- Finalize the architecture and phases together before rebuilding application
  code. A proposal in either document is not an approved implementation task.
- Maintain exactly two documents for the rebuild: this Architecture Document and
  the [Implementation Details Document](IMPLEMENTATION_DETAILS.md). Product scope,
  UX flows, decision records, and system diagrams belong here. Detailed contracts,
  phases, tasks, and verification instructions belong in the implementation document.
  The requested HTML prototype may accompany them as a visual design asset.
- Previous project documentation is superseded for the rebuild. Carry applicable
  information into these two documents instead of requiring legacy plans as
  additional sources of truth. The current login requirements supersede older
  instructions that prohibit users and authentication.

## 4. Core user journey and UX proposals

Installation: configure the application and model connections → start with Docker
Compose → complete the agreed account setup. The exact first-run flow is open.

Learning: sign in → start or resume a discussion → ask follow-up questions → generate a
summary → review and save knowledge → return to the library → ask a question
across saved knowledge and open its supporting entries.

Investor demo: open the demo page → explore the learning flow. Whether this uses
clearly labeled sample responses or a restricted live backend is currently open.

Summary review/editing and explicit confirmation are agreed under D-03. The
landing screen and navigation remain open. Knowledge questions search confirmed
summaries; full transcripts remain available to reopen under D-04.

Proposed UX criteria:

- Make the next useful action clear in both a first visit and a return visit.
- Preserve work through navigation and recoverable failures.
- Show understandable progress, failure, retry, and save states.
- Support keyboard use, accessible content, and small screens.
- Validate the main journey with realistic learning tasks before finalizing it.

### Interactive design reference

The founder requested a prompt for Claude to create an interactive HTML design
artifact and a downloadable file. The self-contained prompt is stored in
[Implementation Details, section 7](IMPLEMENTATION_DETAILS.md#7-design-prototype-prompt).

The founder supplied [learntrail-v1-design.html](learntrail-v1-design.html). Its
source and declared assumptions have been inspected; browser rendering and its
embedded claims of verification have not been independently checked. It is a
visual reference alongside the two written documents.

The prototype includes account entry, conversations, summary review, a knowledge
library, knowledge questions, and source inspection. It explicitly marks its
model labels, summary structure, retained-draft behavior, coverage handling, and
other design details as proposals. Saving the artifact does not finalize those
open choices. The prototype predates self-hosted setup and the latest login choices;
those screens will need to follow D-09/D-10. The production technology choice is
recorded separately in D-05.

The demo should follow the evolving product design. The supplied prototype is a
design reference, not proof that the real learning backend has been implemented.

## 5. Candidate responsibilities and data flow — proposed

React owns the frontend and FastAPI owns the backend under D-05. The following
responsibilities are proposed module boundaries; they do not require separate
deployed services:

- **Application interface:** conversations, summary capture, knowledge library,
  knowledge questions, and account access.
- **Identity and authorization:** provide the selected login methods, identify the
  user, and enforce access to conversations, saved knowledge, and retrieved
  evidence within the installation.
- **Conversation workflow:** assemble relevant shared conversation context, call
  the model selected for the next reply, deliver the answer, and retain the agreed
  conversation history.
- **Knowledge capture:** produce a summary and persist the selected knowledge
  representation with its connection to the source conversation.
- **Knowledge retrieval:** find relevant confirmed summaries belonging to the
  current user and provide them as context for an answer with references to those
  summaries. Drafts and full transcripts are outside knowledge retrieval.
- **Model access:** connect to owner-configured model endpoints, handle supported
  capabilities, and keep stored credentials and model calls on the backend.
- **Installation and configuration:** support reproducible Compose startup,
  persistent data, and configuration of accounts and external/local integrations.
- **Web evidence:** selectively retrieve sources and attach clickable references
  to answers under D-01. Preserve source metadata in confirmed summary versions.

To support D-11/D-12, the proposed implementation uses the same React components
and FastAPI learning workflows across local and eventual hosted deployments.
User-owned records and stable API contracts belong in the core from the start.
The proposed future mobile app uses those APIs. A sample-data demo can reuse the
React UI through a clearly separated demo data adapter.

FastAPI's OpenAPI support can supply contracts for client generation; see the
[official client generation documentation](https://fastapi.tiangolo.com/advanced/generate-clients/).
The generator, API versioning scheme, and mobile technology remain open.

Candidate data flow:

1. An authenticated question reaches the application, which verifies access to
   the conversation before retrieving context or calling a model.
2. The model receives the selected context and, if enabled, retrieved web evidence.
   The application returns the answer and retains content according to the agreed
   persistence policy.
3. Knowledge capture summarizes the conversation and saves the selected material.
   The saved record becomes available for knowledge retrieval.
4. A knowledge question searches only the current user's confirmed summaries.
   The answer links to supporting stored material. The behavior for insufficient
   evidence and any use of outside knowledge must be decided explicitly.

## 6. V1 baseline decisions

| Topic | Decision needed |
| --- | --- |
| Research implementation | API adapter; search results retain title, URL, publisher, and snippet |
| Multiple models | OpenAI-compatible chat endpoint is the v1 contract; compatible local endpoints are supported |
| Knowledge capture | Versioned Markdown summary with title, claims, open questions, and sources |
| Knowledge answers | Confirmed summaries only; cite summaries and state insufficient evidence |
| UX | Supplied HTML is the visual reference; implement accessible core journeys |
| Deployment and stack | Vite React TypeScript, FastAPI Python, PostgreSQL/pgvector, Compose web/API/db |
| Installation access | Multi-user; first account is instance admin; admin can disable registration |
| Investor demo | Public synthetic sample-data page; local app is used for live presentations |
| Cost controls | Per-install request, token, concurrency, and tool limits; unknown prices stay unknown |
| Operations | Health checks, redacted logs, backup/restore instructions, migration checks |
| Security | Secure HTTP-only sessions, Argon2id, OAuth state validation, ownership and CSRF checks |
| Development harness | Make targets plus Compose; lint, typecheck, tests, and smoke checks locally and in CI |
| CI/CD | GitHub Actions pull-request gates; tagged immutable images and reviewed demo releases |
| Multi-agent workflow | Bounded tasks, isolated branches/worktrees, serialized schema edits, review gates |
| Future expansion | Versioned API supports hosted credits and mobile later; billing/mobile tooling deferred |

Record future choices and their rationale in this document; do not create
separate decision files.

## 7. Agreed decisions

### D-01 — Search when needed and show clickable sources

**Status:** agreed with the founder.

**Choice:** normal learning conversations can search the web when needed and
must show clickable sources for answers that use web evidence.

**Rationale:** support factual research within a deep conversation while allowing
follow-up explanations that do not require another search.

**Implementation implications:** the conversation workflow needs a search
capability and a way to associate retrieved sources with an answer. Source links
must come from retrieved results, not invented references. Do not label every
answer as verified merely because a model was prompted to be factual.

**V1 resolution:** use an API web-search adapter. Retrieved title, URL, publisher,
and snippet are retained with the reply; knowledge answers never silently mix web
results into stored-knowledge context.

Web search integrations can return sources alongside generated answers; see the
[AI SDK web search examples](https://ai-sdk.dev/cookbook/node/web-search-agent).
This is feasibility research, not a selection of AI SDK or a provider.

### D-02 — Shared conversation with model choice for each reply

**Status:** agreed with the founder.

**Choice:** keep one shared conversation and let the user select the model for
each reply.

**Rationale:** seek different models' perspectives without restarting or manually
copying the discussion.

**Implementation implications:** a selection affects the next generated reply.
Changing models does not replace previous messages. Assemble relevant visible
conversation context for the selected model, including replies from other models.
Record which model produced each assistant reply.

**V1 resolution:** use an OpenAI-compatible adapter with per-installation base URL,
model name, and server-side credential. Record the selected model on each reply;
unavailable models return a retryable error.

### D-03 — Review a summary before saving knowledge

**Status:** agreed with the founder.

**Choice:** generate a summary, let the user review or edit it, and save it as
knowledge only when the user confirms.

**Rationale:** the user controls the conclusions retained from an exploratory
discussion and can correct the generated summary before saving it.

**Implementation implications:** distinguish a summary draft from saved knowledge.
Confirming saves the reviewed version. Generating, editing, or abandoning a draft
does not itself add an entry to the saved knowledge base.

**V1 resolution:** summaries use Markdown plus structured title, claims, open
questions, and sources. Saving creates a version; later edits create a new
confirmed version. Transcript retention and retrieval scope are settled by D-04.

### D-04 — Search confirmed summaries and keep conversations available

**Status:** agreed with the founder.

**Choice:** knowledge questions search confirmed summaries only. Retain full
conversations so the user can reopen them.

**Rationale:** the searchable knowledge base consists of material the user chose
to keep, while the original discussion remains available for reference.

**Implementation implications:** index only confirmed summaries for knowledge
retrieval. Exclude unconfirmed drafts and full transcripts from that retrieval
path. Preserve the connection from each saved summary to its source conversation.
Opening a conversation does not automatically include its transcript in a
knowledge answer. Enforce ownership when retrieving a summary or reopening a chat.

**V1 resolution:** users can archive saved summaries. Confirmed versions are
indexed before a successful save response, and results link to the summary and
source conversation.

### D-05 — FastAPI backend and React frontend

**Status:** selected by the founder.

**Choice:** use Python/FastAPI for the backend and React for the frontend.

**Rationale:** the founder's technology preference for a practical, working
portfolio release.

**Implementation implications:** define an explicit HTTP/streaming contract
between the frontend and API. The backend owns authorization, persistence,
knowledge retrieval, and model/search calls. Provider credentials remain on the
server. A previous proposal for a single TypeScript application is not selected.

**V1 resolution:** Vite/React/TypeScript, FastAPI/Python, PostgreSQL with pgvector,
SQLAlchemy/Alembic, and SSE for streamed responses. Use `frontend/`, `backend/`,
`infra/`, and `tests/` top-level areas.

### D-06 — Practical development setup independent of installed skills

**Status:** requirements specified by the founder; concrete tooling pending.

**Choice:** include a development harness, CI/CD, and multi-agent development
workflows. The setup must be skills-agnostic and avoid overengineering.

**Implementation implications:** development and verification must be accessible
through repository commands and the two maintained documents. Any coding agent
or human developer should be able to follow those contracts without a mandatory
skill package or a particular assistant subscription. Define bounded tasks,
isolated changes, review, and integration for multiple agents.

**V1 resolution:** Make targets wrap formatting, lint, typecheck, tests, Compose,
migrations, and smoke checks. GitHub Actions runs the same gates; agents use
isolated branches with one integrator and mandatory checks.

### D-07 — $10 founder-operated service budget

**Status:** amount agreed previously; scope now applied to investor-demo planning
under D-11. Individual installations fund their own operation under D-09.

Keep the existing US$10 monthly target for the founder's demo infrastructure and
any live model/search use when evaluating demo options. The self-hosted version
uses each operator's infrastructure and model connections; do not force a $10
software limit on all installations. Keep their resource and spending controls
configurable.

**V1 resolution:** the investor page uses synthetic fixtures and no model calls;
the local application is the live demonstration. Unknown provider prices remain
unknown and never become zero silently.
Ordinary tests should continue to run without paid model or search calls. The
budget is a planning limit, not a guarantee that unbounded use is affordable.

### D-08 — Security as a top priority

**Status:** priority specified by the founder. Detailed controls will be completed
with the hosting, authentication, data, and development decisions.

**Choice:** protect accounts, private conversations and summaries, configured
credentials, and each operator's resources from the start of implementation.

**Baseline to carry into the design:**

- Authenticate protected API requests and check ownership on every read/write,
  including retrieval, source links, and background work. The server derives the
  acting identity from a verified session, not a browser-supplied user ID.
- Keep provider keys and privileged database credentials on the server, with
  separate credentials for development, preview, and production as applicable.
- Use maintained identity/session components and least-privilege access. Choose
  cookie/token handling, CSRF protection, CORS, and logout/revocation behavior
  together with the eventual authentication integration.
- Treat user input, model output, retrieved summaries, and web content as untrusted
  content. Render generated text safely and validate source URLs. Model prompts
  cannot grant permissions or approve saves. Restrict URLs fetched for research so
  external content cannot direct the backend to internal services. Separately,
  explicitly configured local model endpoints may use private addresses; only
  trusted connection configuration can authorize those destinations.
- Enforce limits on requests, concurrency, tokens, and tool calls on the server.
  Apply configured per-installation limits and, if multi-user access is selected,
  per-user allowances. Account creation must not grant authority to spend another
  person's model credentials.
- Keep sensitive content and secrets out of ordinary logs and agent handoffs.
  Development agents and untrusted CI jobs do not need production credentials.
- Include meaningful security checks in feature acceptance and CI: cross-user
  access, unconfirmed-content exclusion, safe rendering, limited tool privileges,
  spending controls, and dependency/secret checks. Include data recovery in the
  release plan.

These controls follow the principles in the
[OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
and [OWASP prompt-injection guidance](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html).
They are design requirements to implement and verify, not a claim of security
certification or a reason to introduce additional paid security services by default.

### D-09 — Self-hosted Docker Compose release with user model connections

**Status:** selected by the founder as the primary product distribution. A separate
investor demo is required under D-11; paid hosting is a future direction under D-12.

**Choice:** people install Nuroli easily through Docker Compose and connect
their own models.

**Rationale:** make the product useful independently of a founder-operated service
and let operators choose their model providers or local runtimes.

**Implementation implications:** define a small production Compose deployment,
persistent data, a short setup path, versioned releases, and install/upgrade checks.
Model credentials are supplied by the operator and retained server-side. Describe
supported interfaces and capabilities explicitly; compatibility with arbitrary
models is not a verified capability merely because an endpoint is configurable.
Model selection, shared conversations, summary review, and summary-only retrieval
remain required under D-01 through D-04.

**V1 resolution:** each installation supports multiple users. The first account is
the instance administrator; registration can be disabled by that administrator.
Compose exposes only the web port by default; remote access requires an
operator-managed HTTPS reverse proxy.

### D-10 — Google sign-in and email/password

**Status:** selected by the founder in the latest authentication choice.

**Choice:** support Google sign-in and email/password for the self-hosted version.

**Implementation implications:** use maintained authentication components, safe
password hashing, verified OAuth identities, and an explicit account-linking
policy. Do not auto-link accounts using unverified email addresses. Define secure
session, reset/recovery, and signup behavior for the selected installation scope.

Google login requires OAuth configuration, including registered callback URLs;
see [Google's web-server OAuth documentation](https://developers.google.com/identity/protocols/oauth2/web-server).
For easy installation, Google credentials are supplied by the operator through
environment configuration. A shared central login service is not selected.
Password storage should follow
[OWASP guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

**V1 resolution:** use a maintained OAuth client and Argon2id password hashes.
Sessions are secure HTTP-only cookies with CSRF protection. Email verification and
password recovery activate when SMTP is configured; local installs may disable
those flows explicitly.

### D-11 — Local product plus investor demo

**Status:** selected for v1.

**Choice:** people run the real product locally; the founder also has a demo page
for presenting the product to investors.

**Rationale:** support practical use and give the founder an accessible product
showcase.

**Implementation:** share product UI/components and learning contracts. The public
demo clearly identifies simulated behavior, uses synthetic fixtures, and needs no
credentials or paid calls. The Compose app is used for live demonstrations and
never exposes the founder's private local knowledge.

The demo has no client-controlled authorization bypass; a future restricted live
demo can reuse the API with server-enforced access and budgets.

### D-12 — Future paid hosting and mobile client

**Status:** longer-term direction stated by the founder; future implementation.

**Intent:** eventually offer hosted accounts where users can pay or add credit and
store learnings, and build a mobile application.

**Design consequences to preserve now:** keep user ownership explicit in stored
records and API access; keep learning logic, model calls, and permission checks in
FastAPI; use documented client-independent API contracts. Reuse that core when
adding hosted deployment and a mobile client. Keep model-usage accounting separate
from future payment collection so it can support paid access later.

**Future decisions:** pricing/credit semantics, payment provider and reliable
payment events, account balances, hosting scale, mobile technology and sessions,
and any migration or synchronization between local and hosted knowledge. Do not
assume that adding a mobile client automatically synchronizes separate local
installations. Wallet/billing code and the mobile app belong in later phases.

## 8. Implementation readiness

The v1 architecture is finalized for implementation. Remaining choices are
task-level details such as package pins, copy, visual refinements, and additional
provider adapters. They must not change ownership, confirmation, retrieval, or
credential boundaries without updating this document.
