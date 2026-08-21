/**
 * The typed backend client.
 *
 * Every request shape here is derived from `schema.gen.ts`, which is generated
 * from the backend's own OpenAPI document — so the Pydantic models are the
 * single source of truth (CLAUDE.md invariant #4) and a renamed field becomes a
 * TypeScript error here rather than an `undefined` at runtime.
 *
 * docs/CODE_QUALITY.md is explicit that hand-written Zod schemas for API shapes
 * are *not* allowed for exactly this reason: they would be a second source of
 * truth that drifts silently. Zod is for purely-local form state only.
 *
 * Regenerate with `pnpm --filter web openapi:gen` after any endpoint change.
 */

import createClient from "openapi-fetch";
import type { components } from "./schema.gen";

/**
 * Where the backend lives, from the browser's point of view.
 *
 * `NEXT_PUBLIC_` because this is read in the browser — and note what that means:
 * anything with this prefix is shipped to the client and is therefore public by
 * construction. A model-provider credential must never acquire this prefix
 * (CLAUDE.md invariant #3). This is a URL, which is safe to expose.
 *
 * The container reaches the API at `http://backend:8000` on the compose network,
 * but this value is resolved by the *browser*, which is outside it — hence
 * localhost.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Where the browser reaches the trace viewer (Phase 5).
 *
 * Also a URL and also resolved outside the compose network, so also localhost —
 * the backend exports spans to `http://phoenix:6006`, which means nothing here.
 */
export const PHOENIX_URL = process.env.NEXT_PUBLIC_PHOENIX_URL ?? "http://localhost:6006";

/**
 * A deep link to one trace.
 *
 * The single place in the frontend that knows the trace backend's URL shape.
 * `docs/decisions/0002-no-otel-collector.md` keeps the *instrumentation* vendor
 * neutral; a clickable link cannot be — someone has to know what a Phoenix URL
 * looks like. Confining it to one function is what makes swapping the backend a
 * one-function edit rather than a search.
 */
export function traceUrl(traceId: string): string {
  return `${PHOENIX_URL}/projects/default/traces/${traceId}`;
}

export const api = createClient<import("./schema.gen").paths>({ baseUrl: API_BASE_URL });

/** A chat without its transcript — what the sidebar lists. */
export type Chat = components["schemas"]["ChatRead"];
/** A chat with its full transcript — what resuming returns. */
export type ChatDetail = components["schemas"]["ChatDetail"];
/** One persisted turn. */
export type Message = components["schemas"]["MessageRead"];

/**
 * One approved Learning that supplied context for an answer, and the passage it
 * supplied (Phase 8).
 *
 * Built by the backend from the retrieval record, never parsed out of the answer
 * text — so it says what was actually retrieved rather than what the model
 * claimed about its own reasoning.
 */
export type Citation = components["schemas"]["Citation"];
/** An answer grounded in approved Learnings, with its sources. */
export type AskResponse = components["schemas"]["AskResponse"];

/**
 * A model-generated summary awaiting review. **Not knowledge.**
 *
 * The type is distinct from `Learning` for the same reason the tables are: a
 * draft is something the model proposed, a Learning is something the user
 * accepted. Sharing a type would make it possible to render one as the other.
 */
export type SummaryDraft = components["schemas"]["SummaryDraftRead"];
/** The editable body shared by a draft and a Learning. */
export type SummaryContent = components["schemas"]["SummaryContent"];
/** An approved Learning — the library list view. */
export type Learning = components["schemas"]["LearningRead"];
/** An approved Learning with its full revision history. */
export type LearningDetail = components["schemas"]["LearningDetail"];
/** One version of a Learning's content. */
export type LearningRevision = components["schemas"]["LearningRevisionRead"];

/** Per-alias usage over a window — the model-comparison dashboard (Phase 10). */
export type ModelComparison = components["schemas"]["ModelComparison"];
/** One alias's row in that comparison. */
export type ModelUsage = components["schemas"]["ModelUsage"];

/**
 * The narrative fields, in the order they are shown.
 *
 * Declared once so the review editor and the read-only views cannot drift into
 * showing different fields — which would let a user approve a draft without
 * having seen part of it.
 */
export const SUMMARY_FIELDS = [
  "key_concepts",
  "distinctions",
  "examples",
  "open_questions",
  "uncertainty_notes",
  "suggested_tags",
] as const satisfies readonly (keyof SummaryContent)[];

export type SummaryListField = (typeof SUMMARY_FIELDS)[number];

/** Human-readable labels for those fields. */
export const FIELD_LABELS: Record<SummaryListField, string> = {
  key_concepts: "Key concepts",
  distinctions: "Distinctions",
  examples: "Examples",
  open_questions: "Open questions",
  uncertainty_notes: "Uncertainty",
  suggested_tags: "Tags",
};

/**
 * Pull the editable body out of a draft or Learning's `structured_content`.
 *
 * That field is typed as an open record by openapi-typescript, because the
 * backend stores it as JSONB. This is the one place that narrowing happens, so
 * the assertion is written down once rather than scattered across components.
 */
export function toContent(structured: Record<string, unknown>): SummaryContent {
  return structured as unknown as SummaryContent;
}

/**
 * One list field, always an array.
 *
 * The generated types mark these optional because the backend gives them
 * defaults, so a payload may legitimately omit an empty list. Under
 * `noUncheckedIndexedAccess` every read would otherwise need its own `?? []`,
 * and one forgotten instance is a crash while rendering a Learning. Narrowing
 * once here keeps that impossible.
 */
export function listField(content: SummaryContent, field: SummaryListField): readonly string[] {
  return content[field] ?? [];
}
