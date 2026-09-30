/**
 * Follow the rep's live call (GET /live-calls/stream).
 *
 * The Chrome extension reports calls placed from HubSpot; the backend streams
 * the rep's current call here with the contact already resolved. No `@/`
 * imports: this file runs under node --test.
 */

export type LiveCallStatus = "dialing" | "connected" | "ended" | "completed";

export interface LiveCall {
  external_call_id: string;
  provider: string;
  source: string;
  status: LiveCallStatus;
  direction: "outbound" | "inbound";
  remote_number: string | null;
  started_at: number;
  updated_at: number;
  contact_id: string | null;
  contact_name: string | null;
  contact_source: "page" | "phone" | null;
  page_object_type: "contact" | "company" | "deal" | null;
  page_record_id: string | null;
  answered_at: number | null;
  ended_at: number | null;
  end_status: string | null;
  engagement_id: string | null;
}

export type LiveCallStreamEvent =
  | { type: "snapshot"; call: LiveCall | null }
  | { type: "call"; call: LiveCall };

export function isLiveCallOpen(call: LiveCall | null | undefined): call is LiveCall {
  return call?.status === "dialing" || call?.status === "connected";
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
        if (event?.type === "snapshot" || (event?.type === "call" && event.call)) onEvent(event);
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
  onCall: (call: LiveCall | null) => void;
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
  onCall,
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
              onCall(event.call),
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
