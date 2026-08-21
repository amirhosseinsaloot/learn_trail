/**
 * The model-comparison dashboard (docs/SPEC.md §15, Phase 10).
 *
 * Reads `/models/comparison` and shows, per alias, what routing actually cost:
 * how many requests each model served, the money and the latency. This is the
 * page that makes the routing decision reviewable — the whole reason to route by
 * difficulty is the quality-versus-cost trade-off, and a trade-off you cannot see
 * is one you cannot tune.
 *
 * A client component because the window is interactive. It holds no credential
 * and calls only the backend (CLAUDE.md invariant #3).
 */

"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type ModelComparison } from "@/lib/api/client";

const WINDOWS = [
  { label: "24 hours", hours: 24 },
  { label: "7 days", hours: 24 * 7 },
  { label: "30 days", hours: 24 * 30 },
] as const;

export default function ModelsPage() {
  const [comparison, setComparison] = useState<ModelComparison | null>(null);
  const [windowHours, setWindowHours] = useState<number>(24 * 7);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async (hours: number) => {
    const { data, error } = await api.GET("/models/comparison", {
      params: { query: { window_hours: hours } },
    });
    if (error !== undefined) {
      setNotice("could not load model usage — is the backend running?");
      return;
    }
    setComparison(data);
    setNotice(null);
  }, []);

  useEffect(() => {
    void refresh(windowHours);
  }, [refresh, windowHours]);

  const rows = comparison?.usage ?? [];
  const totalCost = rows.reduce((sum, row) => sum + row.total_cost, 0);
  const totalRuns = rows.reduce((sum, row) => sum + row.runs, 0);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-10">
      <header className="flex items-baseline justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight text-white">Model usage</h1>
          <p className="text-sm text-slate-500">
            What routing cost. Simple questions go to the fast model, harder ones to the strong one
            — this is the difference that buys.
          </p>
        </div>
        <Link href="/" className="text-sm text-sky-400 hover:text-sky-300">
          ← Back to chat
        </Link>
      </header>

      <div className="flex gap-2">
        {WINDOWS.map((option) => (
          <button
            key={option.hours}
            type="button"
            onClick={() => {
              setWindowHours(option.hours);
            }}
            className={`rounded border px-3 py-1.5 text-sm ${
              option.hours === windowHours
                ? "border-sky-500 text-sky-300"
                : "border-slate-700 text-slate-400 hover:border-slate-500"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {notice !== null && (
        <p role="status" className="text-sm text-amber-300">
          {notice}
        </p>
      )}

      {rows.length === 0 ? (
        <p className="text-sm text-slate-600">No model calls in this window yet.</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-widest text-slate-500">
            <tr>
              <th className="py-2">Model</th>
              <th className="py-2 text-right">Requests</th>
              <th className="py-2 text-right">Total cost</th>
              <th className="py-2 text-right">Avg latency</th>
              <th className="py-2 text-right">Tokens (in / out)</th>
            </tr>
          </thead>
          <tbody className="text-slate-300">
            {rows.map((row) => (
              <tr key={row.model_alias} className="border-t border-slate-800">
                <td className="py-2 font-medium text-slate-100">{row.model_alias}</td>
                <td className="py-2 text-right">{row.runs}</td>
                <td className="py-2 text-right">${row.total_cost.toFixed(4)}</td>
                <td className="py-2 text-right">{Math.round(row.avg_latency_ms)} ms</td>
                <td className="py-2 text-right text-slate-500">
                  {row.input_tokens} / {row.output_tokens}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t border-slate-700 text-slate-400">
            <tr>
              <td className="py-2">All models</td>
              <td className="py-2 text-right">{totalRuns}</td>
              <td className="py-2 text-right">${totalCost.toFixed(4)}</td>
              <td className="py-2 text-right" />
              <td className="py-2 text-right" />
            </tr>
          </tfoot>
        </table>
      )}
    </main>
  );
}
