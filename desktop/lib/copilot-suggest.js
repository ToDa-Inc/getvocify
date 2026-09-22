import { pushSse } from '../../shared/ui/copilot/suggestion-state.js';
import { liveAssistPayloadFromSuggestEvent } from './live-assist-overlay.js';

let lastRequestedFinalLine = '';

/** Whether a final transcript line should trigger a new /copilot/suggest fetch. */
export function shouldFetchCopilotSuggest(lastRequested, latestTurn) {
  const line = String(latestTurn ?? '').trim();
  if (!line) return false;
  return line !== String(lastRequested ?? '').trim();
}

export function shouldRequestCopilotSuggest(latestTurn) {
  return shouldFetchCopilotSuggest(lastRequestedFinalLine, latestTurn);
}

export function markCopilotSuggestRequested(latestTurn) {
  const line = String(latestTurn ?? '').trim();
  if (line) lastRequestedFinalLine = line;
}

export function resetCopilotSuggestRequestDedupe() {
  lastRequestedFinalLine = '';
}

/** Incrementally parse copilot suggest SSE and emit overlay payloads for result events. */
export function createCopilotSuggestIngester(onPayload) {
  let buffer = '';
  return {
    push(chunk) {
      const next = pushSse(buffer, chunk);
      buffer = next.buffer;
      for (const raw of next.events) {
        let event;
        try {
          event = JSON.parse(raw);
        } catch {
          continue;
        }
        const payload = liveAssistPayloadFromSuggestEvent(event);
        if (payload) onPayload(payload, event);
      }
    },
    reset() {
      buffer = '';
    },
  };
}

export async function streamCopilotSuggest(
  fetchImpl,
  { apiBase, token, body, onPayload, signal } = {},
) {
  const base = String(apiBase || '').replace(/\/+$/, '');
  const res = await fetchImpl(`${base}/copilot/suggest`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    return { ok: false, status: res.status };
  }
  const ingest = createCopilotSuggestIngester(onPayload);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    ingest.push(decoder.decode(value, { stream: true }));
  }
  return { ok: true, status: res.status };
}
