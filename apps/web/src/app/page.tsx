/**
 * The chat page (docs/SPEC.md §6): ask a question, watch the answer stream in,
 * and resume any earlier conversation.
 *
 * A client component in full, because every part of it is interactive state —
 * the chat list, the open transcript, the in-flight answer. There is nothing
 * here worth rendering on the server that would not immediately be replaced.
 *
 * Note what this file cannot do: it holds no credential and calls no model. It
 * talks to the FastAPI backend and nothing else (CLAUDE.md invariant #3).
 */

"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { SummaryReview } from "@/components/SummaryReview";
import {
  API_BASE_URL,
  api,
  type Chat,
  type ChatDetail,
  type SummaryDraft,
  traceUrl,
} from "@/lib/api/client";
import { type AnswerBlocked, type SafetyNotice, streamAnswer } from "@/lib/api/stream";

export default function ChatPage() {
  const [chats, setChats] = useState<readonly Chat[]>([]);
  const [openChat, setOpenChat] = useState<ChatDetail | null>(null);
  const [question, setQuestion] = useState("");
  /** The answer currently arriving, token by token. Null when nothing streams. */
  const [streaming, setStreaming] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** The draft awaiting review for the open chat, if there is one. */
  const [draft, setDraft] = useState<SummaryDraft | null>(null);
  const [summarising, setSummarising] = useState(false);
  /** Safety checks that had something to say about the turn in progress. */
  const [warnings, setWarnings] = useState<readonly SafetyNotice[]>([]);
  const [blocked, setBlocked] = useState<AnswerBlocked | null>(null);

  const refreshChats = useCallback(async () => {
    const { data, error } = await api.GET("/chats", {});
    if (error !== undefined) {
      setNotice("could not load chats — is the backend running?");
      return;
    }
    // No `?? []` fallback: openapi-fetch's result is a discriminated union, so
    // `data` is already known to be present once `error` is undefined. A
    // defensive fallback here would be dead code that type-aware lint flags.
    setChats(data);
  }, []);

  useEffect(() => {
    void refreshChats();
  }, [refreshChats]);

  const openConversation = useCallback(async (chatId: string) => {
    const { data, error } = await api.GET("/chats/{chat_id}", {
      params: { path: { chat_id: chatId } },
    });
    if (error !== undefined) {
      setNotice("could not open that conversation");
      return;
    }
    setOpenChat(data);
    setNotice(null);

    // A draft may already be waiting from a previous visit — it lives in the
    // database, not in this component's state, so reopening the chat must show
    // it rather than silently losing it.
    const pending = await api.GET("/chats/{chat_id}/summary", {
      params: { path: { chat_id: chatId } },
    });
    setDraft(pending.error === undefined ? pending.data : null);
  }, []);

  const send = useCallback(async () => {
    const text = question.trim();
    if (text === "" || busy) return;

    setBusy(true);
    setNotice(null);
    // Per turn, not per session: a warning about the previous question would
    // read as a warning about this one.
    setWarnings([]);
    setBlocked(null);
    try {
      // A chat may not exist yet: the first question creates one. It stays
      // untitled — titles are generated from the conversation later
      // (docs/SPEC.md §6), so inventing one from the first message would
      // pre-empt that.
      let chat: Chat | ChatDetail | null = openChat;
      if (chat === null) {
        const created = await api.POST("/chats", { body: { title: null } });
        if (created.error !== undefined) {
          setNotice("could not start a new chat");
          return;
        }
        chat = created.data;
        setOpenChat(created.data);
      }

      // Two calls, because the backend splits them: appending the question is
      // durable on its own, so a model failure cannot lose what was asked.
      const appended = await api.POST("/chats/{chat_id}/messages", {
        params: { path: { chat_id: chat.id } },
        body: { content: text },
      });
      if (appended.error !== undefined) {
        setNotice("could not send that message");
        return;
      }

      setQuestion("");
      await openConversation(chat.id);
      setStreaming("");

      let received = "";
      const result = await streamAnswer(API_BASE_URL, chat.id, {
        onToken: (fragment) => {
          received += fragment;
          setStreaming(received);
        },
        onError: (detail) => {
          setNotice(detail);
        },
        onSafety: (safety) => {
          setWarnings((previous) => [...previous, safety]);
          if (safety.discard === true) {
            // Pull it off the screen the moment the refusal arrives, rather than
            // waiting for the stream to close. The backend cannot un-send tokens
            // it has already written, so the shortest possible window is the most
            // this layer can offer — and it is worth taking.
            received = "";
            setStreaming(null);
          }
        },
      });

      setStreaming(null);
      if (result.status === "blocked") setBlocked(result.blocked);

      // Name the conversation once it has actually been answered. Only after a
      // real answer: a blocked turn has no assistant content, and titling a chat
      // from a refused question would put the refused subject in the sidebar.
      //
      // The title is generated from the conversation rather than from the first
      // message (docs/SPEC.md §6), and the endpoint refuses to overwrite an
      // existing title — so calling it whenever the open chat looks untitled is
      // safe even if this component's copy is stale. A failure here is left
      // silent on purpose: the answer arrived, and a chat with no name yet is a
      // state the sidebar already renders.
      if (result.status === "done" && chat.title === null) {
        await api.POST("/chats/{chat_id}/title", {
          params: { path: { chat_id: chat.id } },
        });
      }
      // Re-read from the backend rather than appending the accumulated text
      // locally. The database is the source of truth, and re-reading is what
      // makes the screen show what was actually persisted rather than what
      // happened to arrive — which for a blocked answer is nothing at all.
      await openConversation(chat.id);
      await refreshChats();

      if (result.status === "done" && result.done.truncated) {
        setNotice("that answer hit the token limit and is cut off");
      }
    } finally {
      setBusy(false);
    }
  }, [busy, openChat, question, openConversation, refreshChats]);

  const summarise = useCallback(async () => {
    if (openChat === null || summarising) return;
    setSummarising(true);
    setNotice(null);
    try {
      const { data, error, response } = await api.POST("/chats/{chat_id}/summary", {
        params: { path: { chat_id: openChat.id } },
      });
      if (error !== undefined) {
        // 422 is the interesting one: the model produced a summary and it was
        // *rejected* before anything was written (the Phase 3 exit criterion).
        // Saying so plainly is better than "something went wrong", because the
        // user's next move — regenerate — is different from a transport failure.
        setNotice(
          response.status === 422
            ? "the generated summary was rejected before saving; try regenerating"
            : "could not summarise this conversation",
        );
        return;
      }
      setDraft(data);
    } finally {
      setSummarising(false);
    }
  }, [openChat, summarising]);

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl gap-6 px-6 py-10">
      <ChatSidebar
        chats={chats}
        openChatId={openChat?.id ?? null}
        onOpen={openConversation}
        onNew={() => {
          setOpenChat(null);
          setDraft(null);
          setNotice(null);
        }}
      />

      <section className="flex min-w-0 flex-1 flex-col gap-4">
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight text-white">
            {openChat?.title ?? "New conversation"}
          </h1>
          <p className="text-sm text-slate-500">
            Answers are generated server-side through the LiteLLM gateway. Nothing here becomes an
            approved Learning without you saying so.
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <button
              type="button"
              onClick={() => void summarise()}
              disabled={openChat === null || openChat.messages.length === 0 || summarising}
              className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-40"
            >
              {summarising
                ? "Summarising…"
                : draft !== null
                  ? "Regenerate summary"
                  : "Summarise this conversation"}
            </button>
            <Link href="/learnings" className="text-sm text-sky-400 hover:text-sky-300">
              My Learnings →
            </Link>
            <Link href="/models" className="text-sm text-slate-400 hover:text-slate-200">
              Model usage →
            </Link>
          </div>
        </header>

        {notice !== null && (
          <p
            role="status"
            className="rounded border border-amber-500/30 bg-amber-400/10 px-3 py-2 text-sm text-amber-200"
          >
            {notice}
          </p>
        )}

        <SafetyPanel blocked={blocked} warnings={warnings} />

        {draft !== null && (
          <SummaryReview
            draft={draft}
            onApproved={(learningId) => {
              setDraft(null);
              setNotice(`saved to My Learnings (${learningId.slice(0, 8)}…)`);
            }}
            onDismissed={() => {
              setDraft(null);
            }}
          />
        )}

        <Transcript chat={openChat} streaming={streaming} />

        <Composer
          value={question}
          busy={busy}
          onChange={setQuestion}
          onSend={() => {
            void send();
          }}
        />
      </section>
    </main>
  );
}

function ChatSidebar({
  chats,
  openChatId,
  onOpen,
  onNew,
}: {
  readonly chats: readonly Chat[];
  readonly openChatId: string | null;
  readonly onOpen: (chatId: string) => Promise<void>;
  readonly onNew: () => void;
}) {
  return (
    <aside className="flex w-56 shrink-0 flex-col gap-3 border-r border-slate-800 pr-4">
      <button
        type="button"
        onClick={onNew}
        className="rounded border border-slate-700 px-3 py-2 text-left text-sm text-slate-200 hover:border-sky-500 hover:text-sky-300"
      >
        + New conversation
      </button>

      <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">
        Conversations
      </h2>

      {chats.length === 0 ? (
        <p className="text-sm text-slate-600">None yet.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {chats.map((chat) => (
            <li key={chat.id}>
              <button
                type="button"
                onClick={() => {
                  void onOpen(chat.id);
                }}
                className={`w-full truncate rounded px-2 py-1.5 text-left text-sm ${
                  chat.id === openChatId
                    ? "bg-sky-500/10 text-sky-300"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                }`}
              >
                {/* Untitled until a title is generated from the conversation. */}
                {chat.title ?? "Untitled"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

function Transcript({
  chat,
  streaming,
}: {
  readonly chat: ChatDetail | null;
  readonly streaming: string | null;
}) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat, streaming]);

  const isEmpty = chat === null || chat.messages.length === 0;

  return (
    <div className="flex min-h-72 flex-1 flex-col gap-4 overflow-y-auto rounded border border-slate-800 p-4">
      {isEmpty && streaming === null ? (
        <p className="m-auto text-sm text-slate-600">Ask something to start.</p>
      ) : (
        chat?.messages.map((message) => (
          <Turn
            key={message.id}
            speaker={message.role}
            content={message.content}
            traceId={message.trace_id ?? null}
          />
        ))
      )}

      {/* The in-flight answer is not a persisted message yet, so it is rendered
          separately and replaced by the real row once the stream completes. */}
      {streaming !== null && (
        <Turn speaker="assistant" content={streaming === "" ? "…" : streaming} pending />
      )}

      <div ref={bottom} />
    </div>
  );
}

/**
 * One turn in the transcript.
 *
 * The prop is `speaker`, not `role`: `role` is a reserved ARIA attribute, and
 * naming a component prop after it makes accessibility tooling read
 * `speaker="assistant"` as a claim about the element's ARIA role (Biome flags
 * exactly this). `speaker` also says what it means — the author of the message,
 * not the purpose of the element.
 */
function Turn({
  speaker,
  content,
  pending = false,
  traceId = null,
}: {
  readonly speaker: string;
  readonly content: string;
  readonly pending?: boolean;
  readonly traceId?: string | null;
}) {
  const isUser = speaker === "user";
  return (
    <article className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
      <span className="flex items-center gap-2 text-xs uppercase tracking-widest text-slate-600">
        {speaker}
        {/* The Phase 5 criterion, made one click away: "this answer was poor"
            becomes the trace that shows where it went wrong. Only on turns a
            model produced — a user's question has nothing to trace. */}
        {traceId !== null && (
          <a
            href={traceUrl(traceId)}
            target="_blank"
            rel="noreferrer"
            title={`trace ${traceId}`}
            className="normal-case tracking-normal text-slate-600 underline decoration-dotted hover:text-sky-400"
          >
            trace ↗
          </a>
        )}
      </span>
      <p
        className={`max-w-prose whitespace-pre-wrap rounded px-3 py-2 text-sm ${
          isUser ? "bg-sky-500/10 text-sky-100" : "bg-slate-800/60 text-slate-200"
        } ${pending ? "opacity-70" : ""}`}
      >
        {content}
      </p>
    </article>
  );
}

function Composer({
  value,
  busy,
  onChange,
  onSend,
}: {
  readonly value: string;
  readonly busy: boolean;
  readonly onChange: (value: string) => void;
  readonly onSend: () => void;
}) {
  return (
    <form
      className="flex gap-2"
      onSubmit={(submitEvent) => {
        submitEvent.preventDefault();
        onSend();
      }}
    >
      <input
        value={value}
        onChange={(changeEvent) => {
          onChange(changeEvent.target.value);
        }}
        disabled={busy}
        placeholder="Ask a question…"
        aria-label="Your question"
        className="flex-1 rounded border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={busy || value.trim() === ""}
        className="rounded bg-sky-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:opacity-40"
      >
        {busy ? "Answering…" : "Send"}
      </button>
    </form>
  );
}

/**
 * What the safety pipeline decided about this turn (docs/SPEC.md §8).
 *
 * A refusal is shown differently from an error, and the difference is not
 * cosmetic: an error means "try again", a refusal means "this will be refused
 * again". Colouring them the same would teach the user to retry a message that
 * cannot succeed.
 *
 * The categories are shown; the matched text is not, and cannot be — the backend
 * sends categories only, so that an API key found in a message is never copied
 * into a second place.
 */
function SafetyPanel({
  blocked,
  warnings,
}: {
  readonly blocked: AnswerBlocked | null;
  readonly warnings: readonly SafetyNotice[];
}) {
  // A block already has its own panel, so re-listing the check that caused it
  // below would say the same thing twice.
  const advisories = warnings.filter((notice) => notice.discard !== true && blocked === null);
  if (blocked === null && advisories.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      {blocked !== null && (
        <section
          role="alert"
          className="rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-100"
        >
          <p className="font-medium">
            {blocked.stage === "input"
              ? "That question was not sent to the model."
              : "That answer was withheld."}
          </p>
          <p className="pt-1 text-rose-200/80">
            {blocked.explanation === "" ? "A safety check refused this turn." : blocked.explanation}
          </p>
          {blocked.categories.length > 0 && (
            <p className="pt-1 text-xs uppercase tracking-widest text-rose-300/70">
              {blocked.categories.join(" · ")}
            </p>
          )}
          <p className="pt-1 text-xs text-rose-300/70">
            Nothing was saved to this conversation, so it cannot reach a Learning.
          </p>
        </section>
      )}

      {advisories.map((notice) => (
        <section
          key={`${notice.stage}-${notice.categories.join(",")}`}
          className="rounded border border-amber-500/30 bg-amber-400/10 px-3 py-2 text-sm text-amber-200"
        >
          <p>
            {notice.explanation === "" ? "A safety check flagged this turn." : notice.explanation}
          </p>
          <p className="pt-1 text-xs text-amber-300/70">
            Answered anyway — this is a warning, not a refusal. Worth checking before you approve
            anything from this conversation as a Learning.
          </p>
        </section>
      ))}
    </div>
  );
}
