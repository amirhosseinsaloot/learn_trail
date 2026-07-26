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

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL, api, type Chat, type ChatDetail } from "@/lib/api/client";
import { type AnswerDone, streamAnswer } from "@/lib/api/stream";

export default function ChatPage() {
  const [chats, setChats] = useState<readonly Chat[]>([]);
  const [openChat, setOpenChat] = useState<ChatDetail | null>(null);
  const [question, setQuestion] = useState("");
  /** The answer currently arriving, token by token. Null when nothing streams. */
  const [streaming, setStreaming] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
  }, []);

  const send = useCallback(async () => {
    const text = question.trim();
    if (text === "" || busy) return;

    setBusy(true);
    setNotice(null);
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
      const finished: AnswerDone | null = await streamAnswer(API_BASE_URL, chat.id, {
        onToken: (fragment) => {
          received += fragment;
          setStreaming(received);
        },
        onError: (detail) => {
          setNotice(detail);
        },
      });

      setStreaming(null);
      // Re-read from the backend rather than appending the accumulated text
      // locally. The database is the source of truth, and re-reading is what
      // makes the screen show what was actually persisted rather than what
      // happened to arrive.
      await openConversation(chat.id);
      await refreshChats();

      if (finished?.truncated === true) {
        setNotice("that answer hit the token limit and is cut off");
      }
    } finally {
      setBusy(false);
    }
  }, [busy, openChat, question, openConversation, refreshChats]);

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl gap-6 px-6 py-10">
      <ChatSidebar
        chats={chats}
        openChatId={openChat?.id ?? null}
        onOpen={openConversation}
        onNew={() => {
          setOpenChat(null);
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
        </header>

        {notice !== null && (
          <p
            role="status"
            className="rounded border border-amber-500/30 bg-amber-400/10 px-3 py-2 text-sm text-amber-200"
          >
            {notice}
          </p>
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
          <Turn key={message.id} speaker={message.role} content={message.content} />
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
}: {
  readonly speaker: string;
  readonly content: string;
  readonly pending?: boolean;
}) {
  const isUser = speaker === "user";
  return (
    <article className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
      <span className="text-xs uppercase tracking-widest text-slate-600">{speaker}</span>
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
