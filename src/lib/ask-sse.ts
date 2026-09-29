export type AskEvent = { type: string } & Record<string, unknown>;

/** Incremental SSE parser. Returns whole events and the unfinished tail to carry into the next chunk. */
export function parseSse(buffer: string): { events: AskEvent[]; rest: string } {
  const events: AskEvent[] = [];
  let rest = buffer;
  for (;;) {
    const end = rest.indexOf("\n\n");
    if (end === -1) break;
    const block = rest.slice(0, end);
    rest = rest.slice(end + 2);
    for (const line of block.split("\n")) {
      if (!line.startsWith("data:")) continue;
      try {
        const parsed = JSON.parse(line.slice(5).trim()) as AskEvent;
        if (parsed && typeof parsed.type === "string") events.push(parsed);
      } catch {
        // A malformed event is skipped; the stream and the persisted turn stay the source of truth.
      }
    }
  }
  return { events, rest };
}
