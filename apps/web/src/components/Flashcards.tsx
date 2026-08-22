/**
 * Revision flashcards for one Learning (docs/SPEC.md §15, Phase 12).
 *
 * Cards are generated on demand and never stored — they are a study aid derived
 * from approved knowledge, not knowledge itself, so there is nothing to save and
 * "Generate" can simply be pressed again for a fresh set. Each card flips on
 * click: the front is the cue, the back the answer, and hiding the back until
 * asked is the whole point of a flashcard.
 */

"use client";

import { useCallback, useState } from "react";
import { api, type FlashcardSet } from "@/lib/api/client";

export function Flashcards({ learningId }: { readonly learningId: string }) {
  const [set, setSet] = useState<FlashcardSet | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const generate = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setNotice(null);
    try {
      const { data, error } = await api.POST("/learnings/{learning_id}/flashcards", {
        params: { path: { learning_id: learningId } },
      });
      if (error !== undefined) {
        setNotice("could not generate flashcards — try again");
        return;
      }
      setSet(data);
    } finally {
      setBusy(false);
    }
  }, [busy, learningId]);

  return (
    <section className="flex flex-col gap-3 rounded border border-slate-800 p-4">
      <div className="flex items-baseline justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-semibold text-white">Flashcards</h2>
          <p className="text-sm text-slate-500">
            Revision cards from this Learning. Generated fresh each time — nothing is saved.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void generate()}
          disabled={busy}
          className="shrink-0 rounded bg-sky-500 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:opacity-40"
        >
          {busy ? "Generating…" : set === null ? "Generate" : "Regenerate"}
        </button>
      </div>

      {notice !== null && (
        <p role="status" className="text-sm text-amber-300">
          {notice}
        </p>
      )}

      {set !== null && (
        <ul className="flex flex-col gap-2">
          {set.cards.map((card, index) => (
            <Card key={`${String(index)}-${card.front}`} front={card.front} back={card.back} />
          ))}
        </ul>
      )}
    </section>
  );
}

function Card({ front, back }: { readonly front: string; readonly back: string }) {
  const [shown, setShown] = useState(false);
  return (
    <li>
      <button
        type="button"
        onClick={() => {
          setShown((value) => !value);
        }}
        className="w-full rounded border border-slate-800 px-3 py-2 text-left hover:border-slate-600"
      >
        <p className="text-sm text-slate-200">{front}</p>
        {shown ? (
          <p className="pt-1 text-sm text-emerald-300">{back}</p>
        ) : (
          <p className="pt-1 text-xs uppercase tracking-widest text-slate-600">Show answer</p>
        )}
      </button>
    </li>
  );
}
