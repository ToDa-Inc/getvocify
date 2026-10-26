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

const CARD_TIMEOUT_MS = 20_000;

/** The strategic card's result (POST /copilot/live/card): the points result's shape, so applyPoints merges it. */
export type CardResult = Record<string, unknown> & { points?: { id: string }[]; closed?: { id: string; outcome: string }[]; event?: string; read_t?: number | null };

/** POST /copilot/live/card (pilot, flag LIVE_CARD_ENABLED): ONE card or nothing at an automatic checkpoint. */
export function readCard(body: Record<string, unknown>, signal: AbortSignal): Promise<CardResult> {
  return api.post<CardResult>(`/copilot/live/card`, body, { signal, timeoutMs: CARD_TIMEOUT_MS });
}

/** One UI event of the live view (build contract 2026-10-20, §2.4). */
export type LiveUiEvent = {
  kind: string;
  /** When it happened (ISO 8601). */
  at: string;
  point_id?: string;
  step_kind?: "step" | "data" | "goal";
  step_id?: string;
  detail?: Record<string, unknown>;
};

/** At most this many events per request (the endpoint's limit). */
export const EVENTS_PER_REQUEST = 50;

/** POST /copilot/live/events: logging only, never blocks the call. Resolves with the HTTP status (0: not sent). */
export async function postEvents(callId: string, events: LiveUiEvent[]): Promise<number> {
  try {
    await api.post(`/copilot/live/events`, { call_id: callId, events: events.slice(0, EVENTS_PER_REQUEST) }, { timeoutMs: 10_000 });
    return 204;
  } catch (error) {
    return typeof (error as { status?: unknown })?.status === "number" ? (error as { status: number }).status : 0;
  }
}

/** A points reading that is only read for its result (a rewrite, a step question): the tokens are not drawn. */
export async function pointsResult(body: Record<string, unknown>, signal: AbortSignal): Promise<Record<string, unknown>> {
  let result: Record<string, unknown> | null = null;
  await streamPoints(
    body,
    (event) => {
      if (event.type === "result") result = event;
      else if (event.type === "error") throw new LiveBrainError(502, event.message ?? "the live brain could not answer");
    },
    signal,
  );
  if (!result) throw new LiveBrainError(502, "no result");
  return result;
}
