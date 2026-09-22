// Live help is for meetings only. A step is done when evidence names it, not because time passed.

export function assistAllowed({ kind, enabled, playbookReady, evidenceRefs }) {
  if (kind !== "meeting") return { show: false, reason: "not_a_meeting" };
  if (enabled === false) return { show: false, reason: "disabled" };
  if (!playbookReady || !evidenceRefs?.length) return { show: false, reason: "silent" };
  return { show: true, reason: null };
}

export function stepStatus(step, evidenceRefs, elapsedMs = 0) {
  void elapsedMs;
  if (!step?.evidence_ref) return "open";
  return evidenceRefs.includes(step.evidence_ref) ? "done" : "open";
}

export function reduceSuggestion(state, event) {
  if (event.type === "start" || event.type === "switch") {
    return { meetingId: event.meetingId, requestId: null, card: null };
  }
  if (event.type === "cancel") {
    return { ...state, requestId: null, card: null };
  }
  if (event.type === "request") {
    if (event.meetingId !== state.meetingId) return state;
    return { ...state, requestId: event.requestId, card: null };
  }
  if (event.type === "result") {
    if (event.meetingId !== state.meetingId || event.requestId !== state.requestId) return state;
    return { ...state, card: event.card };
  }
  if (event.type === "dismiss") {
    if (event.requestId !== state.requestId) return state;
    return { ...state, card: null };
  }
  return state;
}

export function pushSse(buffer, chunk) {
  const text = `${buffer}${chunk}`;
  const events = [];
  let rest = text;
  while (rest.includes("\n\n")) {
    const index = rest.indexOf("\n\n");
    const frame = rest.slice(0, index);
    rest = rest.slice(index + 2);
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim())
      .join("\n");
    if (data) events.push(data);
  }
  return { buffer: rest, events };
}
