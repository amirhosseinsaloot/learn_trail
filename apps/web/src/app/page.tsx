/**
 * Phase 0 landing page: a static statement of what this app is and what it does
 * not do yet. No data fetching, no client state, no backend call — the first
 * request to apps/api lands in Phase 1 (plans/phase-1.md).
 */

const TOOLING: readonly { readonly name: string; readonly role: string }[] = [
  { name: "Next.js App Router + React", role: "UI shell, server components by default" },
  { name: "TypeScript", role: "strict, with noUncheckedIndexedAccess" },
  { name: "Tailwind CSS", role: "styling (this page is the proof it is wired)" },
  { name: "Biome", role: "formatting and fast, non-type-aware linting" },
  { name: "typescript-eslint", role: "type-aware rules only, no overlap with Biome" },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-8 px-6 py-16">
      <header className="flex flex-col gap-2">
        <h1 className="text-4xl font-semibold tracking-tight text-white">LearnTrail</h1>
        <p className="text-lg text-sky-400">Ask. Understand. Approve. Remember.</p>
      </header>

      <section className="flex flex-col gap-4 text-slate-300">
        <p>
          A single-user AI learning workspace: persistent Q&amp;A conversations distilled into
          Learnings that only become permanent after an explicit human approval.
        </p>
        <p>
          <span className="rounded bg-amber-400/10 px-2 py-1 font-mono text-sm text-amber-300">
            Phase 0 — development environment
          </span>{" "}
          This frontend is a skeleton. There is no chat, no history, no search and no call to the
          backend yet; those arrive from Phase 1 onward.
        </p>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500">
          What Phase 0 establishes here
        </h2>
        <ul className="flex flex-col gap-2">
          {TOOLING.map((tool) => (
            <li
              key={tool.name}
              className="flex flex-col gap-0.5 border-l-2 border-slate-800 pl-4 sm:flex-row sm:gap-3"
            >
              <span className="font-medium text-slate-100">{tool.name}</span>
              <span className="text-slate-400">{tool.role}</span>
            </li>
          ))}
        </ul>
      </section>

      <footer className="border-t border-slate-800 pt-6 text-sm text-slate-500">
        AI work will happen server-side, behind the FastAPI backend and the LiteLLM gateway — the
        gateway itself joins in Phase 1. This app never holds a model-provider credential and never
        calls a model API directly.
      </footer>
    </main>
  );
}
