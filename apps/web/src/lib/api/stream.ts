/**
 * Reading the answer stream.
 *
 * `fetch` + a ReadableStream rather than `EventSource`, for one hard reason:
 * EventSource only issues GET requests, and `POST /chats/{id}/answer` is a POST
 * because it creates a message. There is no way to make EventSource work here.
 *
 * The parsing below is deliberately minimal — it handles exactly the frames the
 * backend emits (`api/sse.py`) rather than the full SSE grammar (no `id:`, no
 * `retry:`, no comment lines). Anything else would be speculative: the producer
 * is ours and it is one file away.
 */

/** What the backend's `done` event carries. Mirrors the payload in api/sse.py. */
export interface AnswerDone {
  readonly message_id: string;
  readonly sequence_number: number;
  /** The model hit its token ceiling — the answer is cut off, not finished. */
  readonly truncated: boolean;
  /** The application's vocabulary (`learning-fast`), not a provider model name. */
  readonly alias: string;
  /** What actually served it, e.g. `gpt-4o-mini`. */
  readonly provider_model: string;
  readonly input_tokens: number;
  readonly output_tokens: number;
}

/**
 * A safety check that had something to say (Phase 4).
 *
 * Emitted mid-stream rather than summarised at the end, because an output-stage
 * refusal arrives *after* tokens have been rendered: the sooner this lands, the
 * shorter the window in which a blocked answer is on screen.
 */
export interface SafetyNotice {
  readonly stage: "input" | "output";
  readonly action: string;
  readonly categories: readonly string[];
  readonly explanation: string;
  /** Set on the output stage: what was already rendered must be thrown away. */
  readonly discard?: boolean;
}

/** What the backend's `blocked` event carries when a check refused. */
export interface AnswerBlocked {
  readonly stage: "input" | "output";
  readonly categories: readonly string[];
  readonly explanation: string;
  /** Always false today, and sent explicitly: a refused answer is never stored. */
  readonly persisted: boolean;
}

/**
 * How a stream ended.
 *
 * Three outcomes, not two, and that is the whole point of the type. Before
 * Phase 4 the answer was `AnswerDone | null` — finished or not. A refusal is
 * neither: the system worked exactly as designed and produced no answer. Folding
 * it into `null` would make the UI say "something went wrong" about a decision,
 * and would let a caller forget to discard what it had already drawn.
 */
export type AnswerResult =
  | { readonly status: "done"; readonly done: AnswerDone }
  | { readonly status: "blocked"; readonly blocked: AnswerBlocked }
  | { readonly status: "failed" };

export interface StreamHandlers {
  /** Called for each fragment as it arrives. */
  readonly onToken: (text: string) => void;
  /** Called on a server-reported failure, or if the stream ends without `done`. */
  readonly onError: (detail: string) => void;
  /** Called for each safety check that blocked or warned. Passing checks are silent. */
  readonly onSafety?: (notice: SafetyNotice) => void;
}

/**
 * Stream an answer for a chat, dispatching tokens as they arrive.
 *
 * Returns how it ended rather than handing the outcome to an `onDone` callback:
 * a callback would force the caller to stash the value in a mutable variable
 * that TypeScript cannot narrow afterwards (it cannot see that a closure ran),
 * which then needs a cast to use — a cast that would silently survive the value
 * genuinely being absent.
 *
 * A stream that ends without a terminal event reports through `onError` rather
 * than returning quietly: the backend emits `done` only after persisting, so its
 * absence means nothing was saved — and a UI that left the text on screen as
 * though it had been would be lying.
 */
export async function streamAnswer(
  baseUrl: string,
  chatId: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<AnswerResult> {
  const response = await fetch(`${baseUrl}/chats/${chatId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
  });

  // Validation failures arrive as ordinary status codes, because the backend
  // checks everything it can *before* opening the stream. Once the stream is
  // open a status code is no longer expressible, which is why this branch and
  // the `error` event below both exist.
  if (!response.ok || response.body === null) {
    const detail = await response.text().catch(() => "");
    handlers.onError(detail || `request failed with status ${String(response.status)}`);
    return { status: "failed" };
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  // Chunk boundaries fall wherever TCP decides, so a frame can arrive split in
  // half. Everything after the last complete frame is held here until the rest
  // of it turns up.
  let buffer = "";
  let finished: AnswerDone | null = null;
  let blocked: AnswerBlocked | null = null;

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value;

      // A blank line terminates an SSE event. Anything after the final one is an
      // incomplete frame, so it stays in the buffer.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const parsed = parseFrame(frame);
        if (parsed === null) continue;
        if (parsed.event === "token") {
          handlers.onToken((parsed.data as { text: string }).text);
        } else if (parsed.event === "done") {
          finished = parsed.data as unknown as AnswerDone;
        } else if (parsed.event === "safety") {
          handlers.onSafety?.(parsed.data as unknown as SafetyNotice);
        } else if (parsed.event === "blocked") {
          // Recorded rather than returned from here: the loop still has to drain
          // and release the reader, which the `finally` below does.
          blocked = parsed.data as unknown as AnswerBlocked;
        } else if (parsed.event === "error") {
          handlers.onError((parsed.data as { detail: string }).detail);
          return { status: "failed" };
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  if (blocked !== null) return { status: "blocked", blocked };
  if (finished === null) {
    // The connection closed mid-answer. The backend persists only on completion,
    // so there is no saved answer despite text having appeared on screen.
    handlers.onError("the answer stream ended before it finished; nothing was saved");
    return { status: "failed" };
  }
  return { status: "done", done: finished };
}

function parseFrame(frame: string): { event: string; data: Record<string, unknown> } | null {
  let event = "";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7);
    else if (line.startsWith("data: ")) data = line.slice(6);
  }
  if (event === "" || data === "") return null;
  try {
    return { event, data: JSON.parse(data) as Record<string, unknown> };
  } catch {
    // A malformed payload is a bug in the producer, not something to crash the
    // UI over mid-answer. Skipping keeps the rest of the stream readable.
    return null;
  }
}
