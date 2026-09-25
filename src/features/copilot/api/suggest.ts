import type { SuggestRequest, SuggestStreamEvent } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8888/api/v1";

function getAuthToken(): string | null {
  const stored = localStorage.getItem("vocify_token");
  if (!stored || stored === "undefined" || stored === "null") return null;
  return stored;
}

/**
 * Stream objection coaching suggestions via SSE from the backend.
 */
export async function streamObjectionSuggestion(
  body: SuggestRequest,
  onEvent: (event: SuggestStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const token = getAuthToken();
  if (!token) {
    onEvent({ type: "error", message: "Not signed in" });
    return;
  }

  const res = await fetch(`${API_BASE}/copilot/suggest`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      const raw = data?.detail;
      if (typeof raw === "string") detail = raw;
      else if (raw != null) detail = JSON.stringify(raw);
    } catch {
      /* ignore */
    }
    onEvent({ type: "error", message: detail });
    return;
  }

  if (!res.body) {
    onEvent({ type: "error", message: "No response body" });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const line = part
        .split("\n")
        .map((l) => l.trim())
        .find((l) => l.startsWith("data:"));
      if (!line) continue;
      const raw = line.slice(5).trim();
      if (!raw) continue;
      try {
        const event = JSON.parse(raw) as SuggestStreamEvent;
        onEvent(event);
      } catch {
        /* ignore partial JSON */
      }
    }
  }
}
