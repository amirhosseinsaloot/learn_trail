/**
 * Reviewing a generated summary before it becomes a Learning.
 *
 * This component is where CLAUDE.md invariant #5 meets the user: everything it
 * shows is a *draft*, and the only way past it is an explicit Approve. The
 * wording, the ordering and the affordances are all chosen so that approving
 * cannot feel like the default — Approve sits beside Reject and Regenerate, not
 * alone, and nothing is pre-confirmed.
 *
 * Every field is editable before approving, because the user approves what they
 * are looking at. Approving text they never saw would make the review step
 * theatre.
 */

"use client";

import { useEffect, useState } from "react";
import {
  api,
  FIELD_LABELS,
  listField,
  SUMMARY_FIELDS,
  type SummaryContent,
  type SummaryDraft,
  type SummaryListField,
  toContent,
} from "@/lib/api/client";

export function SummaryReview({
  draft,
  onApproved,
  onDismissed,
}: {
  readonly draft: SummaryDraft;
  readonly onApproved: (learningId: string) => void;
  readonly onDismissed: () => void;
}) {
  const [content, setContent] = useState<SummaryContent>(() => toContent(draft.structured_content));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  // A regenerate replaces the draft entirely, so the editor must reset rather
  // than keep edits made to the previous one — those edits describe text that no
  // longer exists.
  useEffect(() => {
    setContent(toContent(draft.structured_content));
    setDirty(false);
  }, [draft]);

  const save = async (): Promise<boolean> => {
    const { error } = await api.PATCH("/summaries/{draft_id}", {
      params: { path: { draft_id: draft.id } },
      body: content,
    });
    if (error !== undefined) {
      setNotice("could not save those edits");
      return false;
    }
    setDirty(false);
    return true;
  };

  const approve = async () => {
    setBusy(true);
    setNotice(null);
    try {
      // Save first when there are unsaved edits: approving promotes what the
      // *server* holds, so approving without saving would quietly promote the
      // pre-edit text — the exact mismatch this screen exists to prevent.
      if (dirty && !(await save())) return;

      const { data, error } = await api.POST("/summaries/{draft_id}/approve", {
        params: { path: { draft_id: draft.id } },
      });
      if (error !== undefined) {
        setNotice("could not approve this draft");
        return;
      }
      onApproved(data.id);
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    setBusy(true);
    try {
      const { error } = await api.POST("/summaries/{draft_id}/reject", {
        params: { path: { draft_id: draft.id } },
      });
      if (error !== undefined) {
        setNotice("could not discard this draft");
        return;
      }
      onDismissed();
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="flex flex-col gap-4 rounded border border-amber-500/30 bg-amber-400/5 p-4">
      <header className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="rounded bg-amber-400/15 px-2 py-0.5 font-mono text-xs text-amber-300">
            draft — not saved to your Learnings
          </span>
          <span className="font-mono text-xs text-slate-600">{draft.prompt_version}</span>
        </div>
        <p className="text-sm text-slate-400">
          The model wrote this from your conversation. Edit anything that is wrong, then approve it
          — nothing is added to My Learnings until you do.
        </p>
      </header>

      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-widest text-slate-500">Title</span>
        <input
          value={content.title}
          onChange={(event) => {
            setContent({ ...content, title: event.target.value });
            setDirty(true);
          }}
          className="rounded border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-widest text-slate-500">Overview</span>
        <textarea
          value={content.overview}
          rows={4}
          onChange={(event) => {
            setContent({ ...content, overview: event.target.value });
            setDirty(true);
          }}
          className="rounded border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
        />
      </label>

      {SUMMARY_FIELDS.map((field) => (
        <ListEditor
          key={field}
          field={field}
          values={listField(content, field)}
          onChange={(values) => {
            setContent({ ...content, [field]: values });
            setDirty(true);
          }}
        />
      ))}

      {notice !== null && (
        <p role="status" className="text-sm text-amber-200">
          {notice}
        </p>
      )}

      <footer className="flex flex-wrap items-center gap-2 border-t border-slate-800 pt-3">
        <button
          type="button"
          onClick={() => void approve()}
          disabled={busy}
          className="rounded bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-emerald-400 disabled:opacity-40"
        >
          {busy ? "Working…" : "Approve into My Learnings"}
        </button>
        <button
          type="button"
          onClick={() => void save()}
          disabled={busy || !dirty}
          className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:border-sky-500 disabled:opacity-40"
        >
          Save edits
        </button>
        <button
          type="button"
          onClick={() => void reject()}
          disabled={busy}
          className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-400 hover:border-rose-500 hover:text-rose-300 disabled:opacity-40"
        >
          Discard
        </button>
        {dirty && <span className="text-xs text-amber-300">unsaved edits</span>}
      </footer>
    </section>
  );
}

/** A simple one-line-per-entry editor for a list field. */
function ListEditor({
  field,
  values,
  onChange,
}: {
  readonly field: SummaryListField;
  readonly values: readonly string[];
  readonly onChange: (values: string[]) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-widest text-slate-500">
        {FIELD_LABELS[field]}
      </span>
      <textarea
        value={values.join("\n")}
        rows={Math.min(Math.max(values.length, 1), 8)}
        placeholder="One per line"
        onChange={(event) => {
          // Blank lines are dropped rather than sent: the backend rejects blank
          // entries, so submitting them would turn a stray newline into a 422.
          onChange(
            event.target.value
              .split("\n")
              .map((line) => line.trim())
              .filter((line) => line !== ""),
          );
        }}
        className="rounded border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none"
      />
    </label>
  );
}
