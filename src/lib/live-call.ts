/**
 * Follow the rep's CRM presence and live call (GET /live-calls/stream).
 *
 * The Chrome extension reports the record the rep has open; when the desktop
 * starts a call, that record is the contact. No `@/` imports: this file runs
 * under node --test.
 */

export interface RecordPresence {
  provider: "hubspot" | "pipedrive";
  /** Null on a CRM page that is not a record (list, sequence, inbox). */
  object_type: "contact" | "company" | "deal" | null;
  record_id: string | null;
  account_id: string | null;
  seen_at: number;
}

export interface LiveCall {
  id: string;
  status: "live" | "ended";
  started_at: number;
  ended_at: number | null;
  provider: "hubspot" | "pipedrive" | null;
  contact_id: string | null;
  contact_source: "page" | "picked" | null;
  /** The record the call was started from; a deal or company still needs a contact pick. */
  record: RecordPresence | null;
  /** The desktop capture memo reserved for this call. */
  memo_id: string | null;
  needs_contact: boolean;
}

export interface LiveState {
  presence: RecordPresence | null;
  call: LiveCall | null;
}

export type LiveCallStreamEvent = { type: "snapshot" | "update" } & LiveState;

export function isLiveCallOpen(call: LiveCall | null | undefined): call is LiveCall {
  return call?.status === "live";
}

/**
 * Append a chunk to the SSE buffer, emit every complete `data:` event and
 * return what is left. Comments (keepalives) and malformed events are skipped.
 */
export function parseLiveCallSse(
  buffer: string,
  chunk: string,
  onEvent: (event: LiveCallStreamEvent) => void,
): string {
  let rest = (buffer + chunk).replace(/\r\n/g, "\n");
  let end = rest.indexOf("\n\n");
  while (end >= 0) {
    const block = rest.slice(0, end);
    rest = rest.slice(end + 2);
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (data) {
      try {
        const event = JSON.parse(data) as LiveCallStreamEvent;
        if (event?.type === "snapshot" || event?.type === "update") onEvent(event);
      } catch {
        /* skip */
      }
    }
    end = rest.indexOf("\n\n");
  }
  return rest;
}

/** 1s, 2s, 4s … capped at 30s. */
export function liveCallReconnectDelay(attempt: number): number {
  return Math.min(30_000, 1000 * 2 ** Math.max(0, attempt));
}

export interface FollowLiveCallsOptions {
  url: string;
  getToken: () => string | null;
  onState: (state: LiveState) => void;
  onConnectedChange?: (connected: boolean) => void;
  signal: AbortSignal;
  fetchImpl?: typeof fetch;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

function abortableSleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

/**
 * Keep a stream open until `signal` aborts, reconnecting with backoff. Each
 * connection starts with a snapshot, so a reconnect never misses the call.
 */
export async function followLiveCalls({
  url,
  getToken,
  onState,
  onConnectedChange,
  signal,
  fetchImpl = fetch,
  sleep = abortableSleep,
}: FollowLiveCallsOptions): Promise<void> {
  let attempt = 0;
  while (!signal.aborted) {
    const token = getToken();
    if (token) {
      try {
        const res = await fetchImpl(url, {
          headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
          signal,
        });
        if (res.ok && res.body) {
          attempt = 0;
          onConnectedChange?.(true);
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer = parseLiveCallSse(buffer, decoder.decode(value, { stream: true }), (event) =>
              onState({ presence: event.presence ?? null, call: event.call ?? null }),
            );
          }
        }
      } catch {
        /* network error or abort: fall through to backoff */
      }
      onConnectedChange?.(false);
    }
    if (signal.aborted) break;
    await sleep(liveCallReconnectDelay(attempt), signal);
    attempt += 1;
  }
}
