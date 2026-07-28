/**
 * My Learnings — everything the user has approved (docs/SPEC.md §6).
 *
 * Only approved Learnings appear here. Drafts live on the chat page behind the
 * review step, which is what makes this list trustworthy: if it is here, someone
 * chose to keep it.
 */

"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AskLearnings } from "@/components/AskLearnings";
import { api, type Learning, toContent } from "@/lib/api/client";

export default function LearningsPage() {
  const [learnings, setLearnings] = useState<readonly Learning[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    const { data, error } = await api.GET("/learnings", {});
    if (error !== undefined) {
      setNotice("could not load your Learnings — is the backend running?");
      return;
    }
    setLearnings(data);
    setLoaded(true);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-10">
      <header className="flex items-baseline justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight text-white">My Learnings</h1>
          <p className="text-sm text-slate-500">
            Approved knowledge. Every entry here was reviewed by you before it was kept.
          </p>
        </div>
        <Link href="/" className="text-sm text-sky-400 hover:text-sky-300">
          ← Back to chat
        </Link>
      </header>

      {/* Placed above the list on purpose: with a library of any size, asking is
          the faster way in than scrolling. Phase 8's whole premise is that the
          library is worth querying rather than only browsing. */}
      <AskLearnings />

      {notice !== null && (
        <p
          role="status"
          className="rounded border border-amber-500/30 bg-amber-400/10 px-3 py-2 text-sm text-amber-200"
        >
          {notice}
        </p>
      )}

      {loaded && learnings.length === 0 ? (
        <p className="rounded border border-slate-800 p-6 text-sm text-slate-500">
          Nothing yet. Have a conversation, then summarise it — the draft will wait here for your
          approval before anything is saved.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {learnings.map((learning) => {
            const content = toContent(learning.structured_content);
            return (
              <li key={learning.id}>
                <Link
                  href={`/learnings/${learning.id}`}
                  className="flex flex-col gap-1 rounded border border-slate-800 p-4 hover:border-sky-600"
                >
                  <span className="font-medium text-slate-100">{learning.title}</span>
                  <span className="line-clamp-2 text-sm text-slate-400">{content.overview}</span>
                  <span className="text-xs text-slate-600">
                    approved {new Date(learning.approved_at).toLocaleDateString()}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
