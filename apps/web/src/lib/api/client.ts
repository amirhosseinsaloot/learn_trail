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

export const api = createClient<import("./schema.gen").paths>({ baseUrl: API_BASE_URL });

/** A chat without its transcript — what the sidebar lists. */
export type Chat = components["schemas"]["ChatRead"];
/** A chat with its full transcript — what resuming returns. */
export type ChatDetail = components["schemas"]["ChatDetail"];
/** One persisted turn. */
export type Message = components["schemas"]["MessageRead"];
