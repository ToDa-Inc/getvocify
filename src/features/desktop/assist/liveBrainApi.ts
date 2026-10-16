import { parseSuggestSseStream } from "../../../../shared/ui/copilot/suggest-stream.js";
import { resolveApiBase } from "@/lib/app-url";
import { api } from "@/shared/lib/api-client";

const API_BASE = resolveApiBase();

/** The points producer's events (SSE): tokens while the model writes, then one result. */
export type PointsEvent =
  | { type: "token"; text: string }
  | ({ type: "result"; producer: "points" } & Record<string, unknown>)
  | { type: "error"; message?: string }
  | { type: "done" };

export class LiveBrainError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "LiveBrainError";
  }
}

function authToken(): string | null {
  try {
    const stored = localStorage.getItem("vocify_token");
    return !stored || stored === "undefined" || stored === "null" ? null : stored;
  } catch {
    return null;
  }
}

/** POST /copilot/live/points: calls `onEvent` for every event; throws a LiveBrainError when the reading cannot be made. */
export async function streamPoints(body: Record<string, unknown>, onEvent: (event: PointsEvent) => void, signal: AbortSignal): Promise<void> {
  const token = authToken();
  if (!token) throw new LiveBrainError(401, "Not signed in");
  const res = await fetch(`${API_BASE}/copilot/live/points`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      /* the status is the answer */
    }
    throw new LiveBrainError(res.status, detail);
  }
  if (!res.body) throw new LiveBrainError(502, "No response body");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer = parseSuggestSseStream(buffer, decoder.decode(value, { stream: true }), (event: PointsEvent) => onEvent(event));
  }
}

const SLOW_TIMEOUT_MS = 20_000;

/** POST /copilot/live/progress (steps, data, goal, Ahora) or /live/recap (Resumen). */
export function readSlow<T>(kind: "progress" | "recap", body: Record<string, unknown>, signal: AbortSignal): Promise<T> {
  return api.post<T>(`/copilot/live/${kind}`, body, { signal, timeoutMs: SLOW_TIMEOUT_MS });
}
