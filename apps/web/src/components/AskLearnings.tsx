/**
 * Ask across My Learnings (docs/SPEC.md §6, Phase 8).
 *
 * **Every answer here shows its sources, and the sources are not optional.** The
 * phase's exit criterion is that an answer identify exactly which approved
 * Learning supplied its context, and a UI that renders the prose while hiding
 * the citations would satisfy the backend and fail the user — the whole point is
 * that you can check where an answer came from.
 *
 * An ungrounded response (`grounded: false`) renders *differently*, not just with
 * an empty source list. "Nothing in your library covers that" and "here is an
 * answer from your library" are different kinds of statement, and showing them in
 * the same box is how a reader comes to believe the second when they were given
 * the first.
 */

"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { type AskResponse, api, type Citation } from "@/lib/api/client";

/**
 * How many passages to retrieve and show.
 *
 * Five is a reading decision as much as a retrieval one: past a handful the model
 * starts averaging across passages instead of using the best, and the source list
 * stops being something a person actually checks.
 */
const SOURCE_LIMIT = 5;

export function AskLearnings() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = useCallback(async () => {
    const text = question.trim();
    if (text === "" || busy) return;

    setBusy(true);
    setError(null);
    try {
      const { data, error: failed } = await api.POST("/learnings/ask", {
        // `limit` is sent explicitly even though the API defaults it. The
        // generated types make it required — openapi-typescript keeps fields
        // that carry a default — and passing it here is the honest reading
        // anyway: how many sources to show is a decision this view is making,
        // not one it should inherit silently.
        body: { question: text, limit: SOURCE_LIMIT },
      });
      if (failed !== undefined) {
        setError("could not search your Learnings");
        return;
      }
      setResult(data);
    } finally {
      setBusy(false);
    }
  }, [busy, question]);

  return (
    <section className="flex flex-col gap-4 rounded border border-slate-800 p-4">
      <header className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-white">Ask across My Learnings</h2>
        <p className="text-sm text-slate-500">
          Answered only from Learnings you approved. Every answer shows which ones it used.
        </p>
      </header>

      <form
        className="flex gap-2"
        onSubmit={(submitEvent) => {
          submitEvent.preventDefault();
          void ask();
        }}
      >
        <input
          value={question}
          onChange={(changeEvent) => {
            setQuestion(changeEvent.target.value);
          }}
          disabled={busy}
          placeholder="What did I learn about…?"
          aria-label="Ask your Learnings"
          className="flex-1 rounded border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={busy || question.trim() === ""}
          className="rounded bg-sky-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:opacity-40"
        >
          {busy ? "Searching…" : "Ask"}
        </button>
      </form>

      {error !== null && (
        <p role="status" className="text-sm text-amber-300">
          {error}
        </p>
      )}

      {result !== null && <Answer result={result} />}
    </section>
  );
}

function Answer({ result }: { readonly result: AskResponse }) {
  // Not grounded: a different statement, rendered as one. Muted and source-less,
  // so it cannot be mistaken for an answer that came from the library.
  if (!result.grounded) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900/40 px-3 py-2">
        <p className="text-sm text-slate-400">{result.answer}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="whitespace-pre-wrap rounded bg-slate-800/60 px-3 py-2 text-sm text-slate-200">
        {result.answer}
      </p>

      <div className="flex flex-col gap-2">
        <h3 className="text-xs uppercase tracking-widest text-slate-500">
          From {countLearnings(result.citations)} of your Learnings
        </h3>
        {result.citations.map((citation) => (
          <Source
            // Keyed by Learning *and* chunk: several passages routinely come from
            // one Learning, so the id alone is not unique within a result set.
            key={`${citation.learning_id}-${String(citation.chunk_index)}`}
            citation={citation}
          />
        ))}
      </div>
    </div>
  );
}

/** Distinct Learnings, not chunks — several passages often come from one note. */
function countLearnings(citations: readonly Citation[]): number {
  return new Set(citations.map((citation) => citation.learning_id)).size;
}

function Source({ citation }: { readonly citation: Citation }) {
  return (
    <article className="rounded border border-slate-800 px-3 py-2">
      <div className="flex items-baseline justify-between gap-2">
        {/* The link is the criterion made usable: from an answer, one click to the
            approved Learning it came from. */}
        <Link
          href={`/learnings/${citation.learning_id}`}
          className="text-sm text-sky-400 hover:text-sky-300"
        >
          {citation.learning_title}
        </Link>
        <span className="shrink-0 text-xs text-slate-600">
          {citation.matched_by} · #{String(citation.chunk_index)}
        </span>
      </div>
      {/* The passage the model was actually given, verbatim. It can differ from
          the Learning as it reads today — the Learning may have been edited since
          — and showing the excerpt is what lets a reader tell. */}
      <p className="whitespace-pre-wrap pt-1 text-xs text-slate-500">{citation.excerpt}</p>
    </article>
  );
}
