/**
 * One Learning: its current content, and every version it has had.
 *
 * The revision history is the point of this page. `change_source` distinguishes
 * text that originated as a generated draft (`model`) from text the user wrote
 * themselves (`human`) — which is what lets someone answer "did I write this, or
 * did I just accept it?" months later. Showing that distinction is the whole
 * reason the column exists, so it is a badge rather than a detail.
 */

"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  FIELD_LABELS,
  type LearningDetail,
  listField,
  SUMMARY_FIELDS,
  type SummaryContent,
  toContent,
} from "@/lib/api/client";

export default function LearningPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [learning, setLearning] = useState<LearningDetail | null>(null);
  const [draft, setDraft] = useState<SummaryContent | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const { data, error } = await api.GET("/learnings/{learning_id}", {
      params: { path: { learning_id: params.id } },
    });
    if (error !== undefined) {
      setNotice("could not load that Learning");
      return;
    }
    setLearning(data);
  }, [params.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const saveEdit = async () => {
    if (draft === null) return;
    setBusy(true);
    try {
      const { error } = await api.PATCH("/learnings/{learning_id}", {
        params: { path: { learning_id: params.id } },
        // The note is what the history will show beside this revision.
        body: { content: draft, note: "edited by hand" },
      });
      if (error !== undefined) {
        setNotice("could not save that edit");
        return;
      }
      setDraft(null);
      await load();
    } finally {
      setBusy(false);
    }
  };

  if (learning === null) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10 text-sm text-slate-500">
        {notice ?? "Loading…"}
      </main>
    );
  }

  const content = toContent(learning.structured_content);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-10">
      <header className="flex flex-col gap-2">
        <Link href="/learnings" className="text-sm text-sky-400 hover:text-sky-300">
          ← My Learnings
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight text-white">{learning.title}</h1>
        <p className="text-xs text-slate-600">
          approved {new Date(learning.approved_at).toLocaleString()}
          {learning.source_chat_id === null && " · source conversation deleted"}
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

      {draft === null ? (
        <>
          <article className="flex flex-col gap-4">
            <p className="whitespace-pre-wrap text-slate-200">{content.overview}</p>
            {SUMMARY_FIELDS.map((field) =>
              listField(content, field).length === 0 ? null : (
                <section key={field} className="flex flex-col gap-1">
                  <h2 className="text-xs uppercase tracking-widest text-slate-500">
                    {FIELD_LABELS[field]}
                  </h2>
                  <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-slate-300">
                    {listField(content, field).map((entry) => (
                      <li key={entry}>{entry}</li>
                    ))}
                  </ul>
                </section>
              ),
            )}
          </article>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                setDraft(content);
              }}
              className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:border-sky-500"
            >
              Edit
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                void (async () => {
                  setBusy(true);
                  await api.DELETE("/learnings/{learning_id}", {
                    params: { path: { learning_id: params.id } },
                  });
                  setBusy(false);
                  router.push("/learnings");
                })();
              }}
              className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-400 hover:border-rose-500 hover:text-rose-300 disabled:opacity-40"
            >
              Delete
            </button>
          </div>
        </>
      ) : (
        <section className="flex flex-col gap-3 rounded border border-sky-600/40 p-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs uppercase tracking-widest text-slate-500">Title</span>
            <input
              value={draft.title}
              onChange={(event) => {
                setDraft({ ...draft, title: event.target.value });
              }}
              className="rounded border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs uppercase tracking-widest text-slate-500">Overview</span>
            <textarea
              value={draft.overview}
              rows={5}
              onChange={(event) => {
                setDraft({ ...draft, overview: event.target.value });
              }}
              className="rounded border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => void saveEdit()}
              className="rounded bg-sky-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:opacity-40"
            >
              Save as new revision
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(null);
              }}
              className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-400"
            >
              Cancel
            </button>
          </div>
        </section>
      )}

      <section className="flex flex-col gap-2 border-t border-slate-800 pt-4">
        <h2 className="text-xs uppercase tracking-widest text-slate-500">Revision history</h2>
        <ul className="flex flex-col gap-2">
          {learning.revisions.map((revision) => (
            <li
              key={revision.id}
              className="flex flex-wrap items-center gap-2 text-sm text-slate-400"
            >
              <span className="font-mono text-xs text-slate-600">v{revision.revision_number}</span>
              {/* The distinction the approval gate exists to preserve: text the
                  model wrote and you accepted, versus text you wrote yourself. */}
              <span
                className={`rounded px-2 py-0.5 font-mono text-xs ${
                  revision.change_source === "model"
                    ? "bg-amber-400/10 text-amber-300"
                    : "bg-sky-500/10 text-sky-300"
                }`}
              >
                {revision.change_source === "model" ? "from model draft" : "your edit"}
              </span>
              {revision.note !== null && <span className="text-slate-500">{revision.note}</span>}
              <span className="text-xs text-slate-600">
                {new Date(revision.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
