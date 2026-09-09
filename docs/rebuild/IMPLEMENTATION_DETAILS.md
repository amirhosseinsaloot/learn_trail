# Implementation Details Document

Status: **Implementation-ready v1 baseline.**

Branch: `rebuild/v1`.
Design authority: [Architecture Document](ARCHITECTURE.md).

## 1. Purpose

Provide sufficiently explicit implementation instructions for smaller, cheaper
AI models to execute the agreed design. The founder should make material product
and architecture decisions; the implementation system should perform the coding,
integration, and verification.

FastAPI and React are selected under D-05. The v1 stack is Vite/React/TypeScript,
FastAPI/Python, PostgreSQL/pgvector, SQLAlchemy/Alembic, and Compose services for
web/API/database. Docker Compose distribution with operator-supplied model
connections is selected under D-09, Google plus email/password login under D-10,
and a public synthetic investor demo under D-11. Paid hosting and a mobile client
are future directions under D-12. Implement tasks in the phases below without
reopening these boundaries.

## 2. Reuse workflow

For each component, once its requirements and technology boundaries are agreed:

1. Inspect relevant, available previous projects or reusable components.
2. Record the candidate's location, what can be reused, its dependencies, and any
   behavior that differs from the required contract in that component's task.
3. Reuse or adapt suitable code when that reduces work without compromising the
   agreed behavior. Implement a new component when there is no suitable candidate.
4. Verify the resulting component against its required behavior, including its
   integration with the rest of this application.

Do not assume old authentication, data ownership, model integrations, tests, or
deployment configuration are suitable without checking them. A previous project's
design does not override the Architecture Document.

## 3. Implementation task contract

Keep all task instructions in this document. Each task must contain the following
before it is marked ready for an implementation model:

| Field | Required detail |
| --- | --- |
| ID and objective | Stable task ID and the observable result |
| Design basis | Agreed architecture decisions and relevant user flow |
| Prerequisites | Completed tasks, exact dependency versions, and required configuration |
| Reuse | Source component, adaptation needed, or reason to implement anew |
| Scope | Exact files or modules to create/change and ownership boundaries |
| Contracts | Types, schema, API inputs/outputs, events, errors, and authorization rules as applicable |
| Behavior | Ordered implementation steps, examples, and relevant failure cases |
| Verification | Exact commands and meaningful acceptance checks |
| Completion | Required working behavior and evidence to report |

Implementation models must use the settled contracts and flag a missing decision
that changes product behavior or architecture. Routine implementation choices
within those contracts belong to the implementation system.

No separate phase documents, prompt files, task specifications, or decision logs
should be created to implement this planning workflow.

## 4. Approved implementation phases

| Phase | Intended usable outcome | Candidate exit evidence |
| --- | --- | --- |
| 0. Harness | Repository layout, Make commands, Compose dev services, CI skeleton | Clean checkout runs formatting, lint, typecheck, tests, and health check |
| 1. Foundation | Multi-user installation, auth, migrations, ownership, baseline UI | Compose login works; data survives restart; cross-user access is rejected |
| 2. Conversations | OpenAI-compatible connection, shared chat, model-per-reply, SSE | Validation, context, streaming, retry, and model attribution pass |
| 3. Research | Configured web-search adapter and clickable source metadata | Search/no-search paths work; links are preserved and safely rendered |
| 4. Capture and review | Summary draft, edit, confirm, versioning, archive, reopen | Cancel does not save; confirmed content is indexed and linked to transcript |
| 5. Knowledge questions | Summary-only vector retrieval and evidence-aware answers | Ownership, citations, partial/insufficient evidence, archive consistency pass |
| 6. Release | Hardened Compose release, backups, upgrade path, security checks | Clean install, restart, upgrade, recovery, and journeys pass |
| 7. Investor demo | Public static sample-data page sharing approved UI patterns | No secrets/model calls; simulated behavior is labeled and isolated |

Split each phase into bounded tasks using the task contract above. Start a task
only when its prerequisites and contracts are written here or in Architecture.
Serialize schema and dependency changes.

Future phases, outside initial release acceptance: paid hosted accounts and
credit/payment handling; a mobile client using the same application API. Scope,
contracts, and release criteria for those phases will be defined later.

## 5. Requirements derived from agreed decisions

### D-01 — Selective web research with clickable sources

- Provide a web research capability within the learning conversation workflow.
- Allow a conversation to answer without searching when research is unnecessary.
- Preserve the association between an answer and the retrieved sources it uses.
- Render those sources as clickable links using returned source metadata.
- Do not implement an unconditional "verified" label for generated answers.

Before preparing implementation tasks, settle the search integration, trigger
rules, citation contract, and research failure behavior. Acceptance checks must
exercise both searched and unsearched answers and verify that source links match
retrieved evidence. There is no selected SDK, provider, or executable task yet.

### D-02 — Model choice within a shared conversation

- Let the user choose which supported model generates the next assistant reply.
- Keep the same conversation and existing messages when the selected model changes.
- Build relevant visible context for the selected model, including earlier replies
  from other models. Do not assume private provider conversation state is portable.
- Record the producing model on each assistant reply.

Implement model configuration, context assembly, selection defaults, and
unsupported/unavailable-model behavior from Architecture. Acceptance checks must cover
a model switch followed by a question that depends on the earlier discussion and
verify that the previous messages and model attribution remain intact.

### D-03 — Review and confirm a summary before saving

- Generate a draft when the user requests a summary.
- Let the user review and edit the draft before confirming a save.
- Save the reviewed content when confirmation succeeds.
- Keep unconfirmed drafts out of the saved knowledge collection.

Implement the summary schema, draft persistence, save contract, versioning, and
archive behavior from Architecture. Acceptance checks must cover editing before
confirmation, abandoning a draft, and confirming the reviewed content. Relevant
failure and retry cases must not silently lose edits or create duplicate entries.

### D-04 — Summary-only knowledge retrieval and retained conversations

- Index and retrieve confirmed summaries for knowledge questions.
- Exclude unconfirmed drafts and full conversation transcripts from that path.
- Persist full conversations and allow their owner to reopen them.
- Maintain the association between a saved summary and its source conversation.
- Apply the current user's ownership boundary to summary retrieval and chat access.

Implement the storage/index schema, indexing lifecycle, archive behavior, and
source-conversation navigation from Architecture. Acceptance checks must
verify that a fact present only in a raw chat or unconfirmed draft cannot enter a
knowledge answer through retrieval, that another user's summaries cannot be
retrieved, and that the owner can reopen the complete source conversation.

### D-05 — FastAPI and React

- Implement the application API in Python using FastAPI.
- Implement the browser interface using React.
- Keep database access, ownership enforcement, knowledge retrieval, and model and
  search integrations behind the API.
- Define request/response schemas and streaming events before frontend and backend
  tasks are assigned independently.

Use Vite/React/TypeScript, the repository layout in Architecture, and its Compose
topology. Do not create another application backend in the frontend.

### D-06 — Development harness, CI/CD, and multiple agents

The following practical baseline is approved. These are setup requirements and
acceptance targets, not implemented commands yet.

**Development harness:** versioned dependency definitions and lockfiles, repeatable
setup, example environment configuration without secrets, clear local run commands,
and the same verification commands usable by developers, agents, and CI. Provide
fast scoped feedback and a complete integration check. Ordinary tests should run
without paid AI/search calls; any live checks need an explicit bounded budget.

**Skills independence:** keep task and working instructions in this document and
expose actions through repository commands. Do not require a SKILL.md file, global
assistant configuration, an assistant-specific plugin, or a paid orchestration
service to develop or verify the project. The two written documents remain the
maintained sources of truth.

**CI/CD:** settle required pull-request checks, secret handling, the container
registry, versioned release gates, migration order, and recovery before configuring
the pipeline. Release images must come from the revision that passed required
checks. Exercise the distributed Compose setup as well as the frontend/API
contract and important user journeys. The required investor demo has its own
delivery configuration, using the shared product source. Do not rely on an
implementation agent's success report alone.

**Multi-agent workflow:** prepare a bounded task and settled contracts first;
give concurrent implementers separate branches/worktrees and non-overlapping
ownership; serialize changes to shared schemas and dependency files; integrate
through a designated owner and review/check gates. Use parallel work only when
tasks can proceed independently. Start with a small, bounded number of agents;
concurrency and cost limits remain to be agreed.

The final setup must document exact commands, environment needs, expected outputs,
failure recovery, and handoff evidence here so smaller implementation models can
execute it without inventing missing architecture.

### D-07 — Cost constraints after the self-hosting change

Use the existing $10 monthly target to evaluate the founder-operated investor
demo. Allocate that amount only after selecting its mode, hosting, and any real
AI/search use. Do not implement a shared founder-funded budget for all local
installations or hard-code $10 as every operator's allowance.

Keep resource controls configurable per installation: context/input size, output
tokens, search iterations, retries, and concurrent generation. Define any monetary
limits only after settling provider usage reporting and price configuration.
Unknown prices must not be treated as zero, and billing alerts are not enforced
limits. If budget reservations are used, handle concurrent requests atomically.
Normal tests remain free of paid calls; explicitly enabled live tests need bounds.

### D-08 — Security requirements throughout implementation

Prepare concrete security acceptance checks alongside each feature's contract.
Use the Architecture Document's baseline as the minimum design scope; exact
libraries and mechanisms depend on the outstanding hosting/authentication choices.

| Boundary | Required implementation and verification focus |
| --- | --- |
| Identity and ownership | Verify the session; reject access to another user's chats, drafts, summaries, and retrieval results; do not trust client-supplied ownership |
| Session and browser | Define cookie/token lifecycle and CSRF/CORS behavior; safely render user/model text; restrict link protocols and any active content |
| Models and research | Treat retrieved content as untrusted; exclude secrets and unauthorized records; permit configured local model endpoints only through trusted connection settings; restrict research URL fetching separately |
| Spending and resources | Enforce configured request, concurrency, token, and tool limits; verify any configured monetary budget under concurrent requests |
| Secrets and delivery | Separate environments; keep production secrets out of developer/agent contexts and untrusted CI; minimize workflow permissions; check dependencies and secret exposure |
| Storage and recovery | Define deletion and index consistency; redact logs; demonstrate the agreed backup/export and recovery process before launch |

Security checks belong in the relevant implementation tasks and required CI gates.
Any deferred control must have a concrete rationale recorded in these documents;
do not weaken ownership or credential boundaries to meet the budget.

### D-09 — Docker Compose installation and model connections

- Prepare a production Compose setup that starts the application and its required
  persistence services after a short configuration step.
- Recommend versioned prebuilt images so installers do not need local Python/Node
  toolchains; registry, container count, and supported host platforms are open.
- Preserve data outside disposable containers and define startup health checks,
  migrations, backup/recovery, and upgrades using released versions.
- Keep database and internal service ports private by default. Decide local access
  defaults, any remote HTTPS setup, and trusted proxy behavior explicitly.
- Configure model connection type, base URL, model identifier, and credentials as
  required by each supported adapter. Do not return stored secrets to the browser.
- Handle cloud endpoints, container service addresses, and host-local model
  runtimes according to the supported installation environments. Container-local
  addresses differ from host addresses; see
  [Docker's Compose networking guide](https://docs.docker.com/compose/how-tos/networking/).
- Validate actual model capabilities needed by chat, structured summaries,
  retrieval embeddings, and optional tool use. Define clear unavailable-feature
  behavior and test each advertised provider interface.
- Define web-search credentials/setup separately from model credentials; connecting
  a model does not establish that live research is available.

Implement installation ownership, service topology, configuration, provider
compatibility, and release format from Architecture. Acceptance must
cover a clean install, retained data after container replacement, supported model
connection tests, rejected invalid configuration, and an upgrade/recovery exercise.
Keep installation instructions in these two documents instead of adding another
maintained setup specification.

### D-10 — Google and email/password authentication

- Support both selected login methods with maintained authentication components.
- Store passwords using an appropriate adaptive password-hashing implementation;
  choose parameters and a library using the current OWASP guidance referenced by
  the Architecture Document. Never store plaintext passwords or log credentials.
- Validate the OAuth callback/session flow, token issuer/audience/expiry, and user
  identity using the selected integration. Register the correct callback URLs.
- Decide account linking explicitly so an unverified email cannot take over an
  existing account. Define owner bootstrap for the chosen installation scope.
- Define email verification, password recovery, session revocation, and login
  throttling. SMTP or another delivery/recovery mechanism remains to be selected.
- Keep provider/client secrets out of version control and shipped images.

Implement the auth integration, first-run setup, Google configuration ownership,
session design, and recovery from Architecture. Acceptance checks
must include invalid/expired sessions, incorrect credentials, OAuth mismatch,
account-linking boundaries, and protected access under the selected owner model.

### D-11 — Local application and investor demo

- Share the React components and learning contracts across the product and demo.
  Use a static synthetic-fixture adapter for the public demo.
- Keep the real local product connected to FastAPI and the operator's configured
  model services. A simulated demo is not acceptance evidence for live integration.
- Label the sample demo clearly, use synthetic fixtures, and avoid credentials or
  paid provider calls. Keep its simulated state separate from the real backend.
- Do not include the founder's private chats, knowledge, local configuration, or
  credentials in demo assets, builds, or seed data.
- Release/demo artifacts must correspond to reviewed and tested product source.

Acceptance checks must verify source sharing, isolation from private data, no
authorization bypass from browser-controlled demo flags, and no-network behavior.

### D-12 — Preserve a path to hosted billing and mobile

For the initial implementation:

- Give stored user content stable IDs and explicit ownership. Apply access checks
  through the API regardless of which client requests the content.
- Keep learning workflows in FastAPI and define HTTP/streaming contracts so the
  web client and a future mobile client can use the same backend behavior.
- Record relevant model usage facts through the model-call boundary, with unknown
  prices represented honestly. Actual user payment balances are a future feature.
- Keep deployment/connection settings separate from learning business rules so
  hosted and local installations can reuse the implementation.

Future tasks will define credit top-ups or other pricing, payment processing and
webhooks, the accounting model, mobile session/storage behavior, and data
migration/synchronization. Do not add payment dependencies, a wallet, or mobile
build tooling to initial tasks merely to reserve this expansion path.

## 6. Implementation defaults and boundaries

The Architecture Document resolves the formerly open choices. Implementers must
use these defaults: multi-user installations with the first account as admin;
secure HTTP-only cookie sessions with CSRF protection; OpenAI-compatible model
connections; SSE responses; PostgreSQL/pgvector; synchronous indexing on confirmed
save; public synthetic demo data; and GitHub Actions gates producing tagged images.

Task-level choices still permitted are exact dependency pins, CSS details, copy,
and additional compatible provider adapters. They must preserve ownership checks,
server-side secrets, confirmed-summary retrieval, explicit save confirmation, and
the no-network behavior of the public demo.

Documentation consolidation belongs in the rebuild work: transfer any applicable
legacy information into these two documents and remove superseded project
documentation as the old application is replaced. Do not delete legacy materials
merely to fill out this planning draft.


## 7. Design prototype prompt

The founder used the following prompt and supplied
[learntrail-v1-design.html](learntrail-v1-design.html). Retain the prompt as the
design brief, with the current architecture decisions taking precedence where
the brief describes earlier open choices. The artifact is a visual reference;
its proposed behavior for gaps in knowledge answers remains pending. FastAPI and
React (D-05), self-hosted installation (D-09), and the latest login methods (D-10)
take precedence over the earlier brief. Installation and connection setup will
need additional UX design within these documents.

```text
Act as a senior product designer and frontend prototyping engineer. Create a polished, interactive design prototype for Nuroli.

Produce an HTML artifact I can preview in Claude and download as one complete file named learntrail-v1-design.html. Build the prototype directly using the brief below. Make reasonable design choices and identify important assumptions in your short handoff.

PRODUCT AND PURPOSE

Nuroli supports how I learn: I ask AI models questions, investigate facts, have deep follow-up conversations, summarize useful conclusions, save that knowledge, and ask questions across it later.

I am the primary user. The product will also let other individual consumers register and log in. It is intended for real use and my professional founder portfolio. Prioritize a thoughtful learning experience, strong visual craft, and clear interactions.

Design from this brief. The previous application's technology, screens, and navigation are not requirements. Production technology and architecture are still being discussed; this HTML prototype is a design reference.

CONFIRMED PRODUCT DECISIONS

1. Users can register, log in, and access their own conversations and knowledge.
2. Chat supports questions and deep follow-up discussions.
3. There is one shared conversation. Users can choose the model for each next reply, while earlier messages remain in the same conversation. Show which model produced each reply.
4. Chat searches the web when needed and displays clickable sources for answers using web evidence.
5. Users request a summary, review or edit the draft, and explicitly confirm before it becomes saved knowledge.
6. Knowledge questions search confirmed summaries only. Unconfirmed drafts and full conversation transcripts are excluded.
7. Full conversations remain available to reopen, including from their saved summaries.

OPEN DECISIONS

Choose a coherent visual style, navigation, screen layout, summary structure, and illustrative model labels for this prototype. These are design proposals, not approved production decisions.

Behavior when saved summaries do not cover a question is also pending. For the prototype, illustrate this proposal: answer supported parts, cite saved summaries, explain gaps, and offer a separate web search. Record this assumption in your handoff and an HTML comment. Do not silently mix outside information into a knowledge answer.

SCOPE AND SCREENS

Create one connected product experience covering:

- Entry and account access: a concise product introduction plus simulated sign-in and registration. Make the main workspace immediately accessible for design review.
- Learning workspace: new and returning-user states, conversation history, readable messages, a composer, model selection, and a clear action to summarize the discussion.
- Research within chat: simulated search progress and clickable source references. Make source inspection easy without losing reading position.
- Summary review: an editable draft with clear confirm-save and cancel/return actions. On desktop, let users refer back to the conversation while reviewing; adapt this comfortably to mobile.
- Knowledge library: saved summaries, useful titles and previews, basic search, and empty/no-results states.
- Saved summary detail: readable content and a way to reopen its original conversation.
- Ask my knowledge: a question interface, an answer supported by confirmed summaries, clickable references opening the relevant saved entries, and examples of partial and missing coverage.

Keep the prototype focused on these flows. Payments, teams, social feeds, gamification, analytics dashboards, uploads, and automatic model debates are outside this design brief.

REQUIRED INTERACTIONS

Make the main controls work with simulated data:

- Start a conversation, send a message, and receive a simulated reply.
- Switch the model for the next reply without losing existing context.
- Show a bounded simulated streaming/search state and a usable stop or retry action.
- Inspect sources and return to the conversation.
- Generate a summary, edit it, cancel without saving, or confirm the edited version.
- A confirmed save adds exactly one entry to the library and shows clear success feedback.
- Search the library, open a saved summary, and reopen its source conversation.
- Ask a sample knowledge question and follow its citations into saved summaries.
- Demonstrate supported, partly supported, and unsupported knowledge answers.
- Preserve draft input and edits during ordinary navigation.
- Provide a clearly separated Reset demo control and a way to preview empty and recoverable-error states.

A clicked control must produce a meaningful result. Use a small, coherent set of seeded conversations and saved summaries so the walkthrough tells a believable story. Simulated answers must be clearly presented as demo behavior. Use real sample source links and do not imply live research has occurred.

VISUAL AND UX DIRECTION

Create one strong, consistent visual concept: calm, focused, readable, and carefully finished. Choose a restrained palette, excellent typography, generous spacing, and clear information hierarchy suited to long reading sessions.

Give the main learning tasks priority. Make new questions, continued conversations, summary drafts, saved knowledge, and knowledge answers easy to distinguish.

Use concise, natural interface copy. Represent product concepts in the UI; keep architecture explanations and design-assumption notes in comments and the handoff.

Use reusable CSS tokens for colors, spacing, type, borders, and elevation. Include consistent focus, hover, disabled, loading, success, and error states.

Support desktop and mobile layouts, including roughly 1440px and 390px widths. Mobile navigation, the composer, and summary review must remain comfortable without horizontal scrolling or hidden controls.

Use semantic HTML, labeled inputs, keyboard-accessible controls, visible focus, sufficient contrast, and reduced-motion support. Manage focus when opening and closing dialogs or drawers. Do not rely on color alone to communicate state.

DELIVERABLE REQUIREMENTS

- One complete HTML file with inline CSS, vanilla JavaScript, and any SVG icons.
- It must work when opened directly in a browser, including offline.
- No build tools, npm installation, CDN scripts, external fonts, remote images, or required network requests. External source links may open when deliberately clicked.
- Use simulated authentication, search, and AI responses. Do not request real credentials or API keys, or connect to a live backend.
- Start with in-memory demo state. If using localStorage, handle unavailable storage gracefully so the artifact still works.
- Keep code organized into clearly commented sections, with shared data and reusable rendering functions.
- Include an HTML comment identifying the prototype as a proposed design reference and listing consequential assumptions.
- Provide the interactive artifact and the complete downloadable HTML file. If direct download is unavailable, provide the entire HTML in one code block, with no omissions.

BEFORE HANDOFF

Walk through: enter the app -> start a conversation -> change model -> inspect sources -> generate and edit a summary -> confirm save -> find it in the library -> ask across saved knowledge -> open a supporting summary -> reopen its conversation.

Also check cancellation, repeated save clicks, empty states, retry behavior, mobile layout, and keyboard navigation. Use available preview/testing tools and state clearly which checks you actually performed.

Keep your final explanation short: the design rationale, important proposed choices, and how to download/open the file. Keep those notes in the chat and HTML comments; no additional specification documents are needed.
```
