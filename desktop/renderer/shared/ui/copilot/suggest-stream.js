import { pushSse } from "./suggestion-state.js";

/** Parse one or more complete SSE data frames from an incremental buffer. */
export function ingestSuggestSseEvents(buffer, chunk) {
  const next = pushSse(String(buffer ?? ""), String(chunk ?? ""));
  const events = [];
  for (const raw of next.events) {
    if (!raw) continue;
    try {
      events.push(JSON.parse(raw));
    } catch {
      /* ignore partial / malformed JSON */
    }
  }
  return { buffer: next.buffer, events };
}

/** Feed SSE chunks and invoke `onEvent` for each parsed JSON payload. */
export function parseSuggestSseStream(buffer, chunk, onEvent) {
  const { buffer: rest, events } = ingestSuggestSseEvents(buffer, chunk);
  for (const event of events) {
    onEvent(event);
  }
  return rest;
}
