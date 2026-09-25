// "Empezar a llamar": Hoy becomes a dial queue. One loop, no navigation.
//   idle → queue(i) → calling(i) → review(i) → queue(i+1) … → done
// Voicemail and no response advance even when a memo exists.
// A failed call stays on the same contact and does not count as done.

export const initialQueue = { mode: "idle" };

const NO_CONVERSATION = new Set(["voicemail", "no_response"]);

export function queueReducer(state, event) {
  switch (state.mode) {
    case "idle":
    case "done":
      if (event.type === "start" && event.items?.length) {
        return { mode: "queue", items: event.items, index: 0 };
      }
      return state;
    case "queue":
      if (event.type === "call") return { ...state, mode: "calling" };
      if (event.type === "skip") return advance(state);
      if (event.type === "exit") return initialQueue;
      return state;
    case "calling":
      if (event.type === "call_ended") return ended(state, event);
      return state;
    case "review":
      if (event.type === "reviewed") return advance(state);
      if (event.type === "exit") return initialQueue;
      return state;
    default:
      return state;
  }
}

function ended(state, event) {
  if (event.callStatus === "failed") {
    return { ...state, mode: "queue", lastOutcome: "failed" };
  }
  if (NO_CONVERSATION.has(event.screeningOutcome)) {
    return advance(state);
  }
  if (event.memoId) return { ...state, mode: "review", memoId: event.memoId };
  return advance(state);
}

function advance(state) {
  const index = state.index + 1;
  if (index >= state.items.length) return { mode: "done", items: state.items };
  return { mode: "queue", items: state.items, index };
}

export function currentItem(state) {
  return state.items && state.index != null ? state.items[state.index] ?? null : null;
}

/** The next contact, if one exists. This does not build a preparation brief. */
export function prefetchTarget(state) {
  if (!["queue", "calling", "review"].includes(state.mode)) return null;
  return state.items[state.index + 1] ?? null;
}

export const QUEUE_KEYS = {
  queue: { Enter: "call", s: "skip", Escape: "exit" },
  review: { n: "reviewed", Escape: "exit" },
};

/** Map a keyboard event to a queue action for the current mode. */
export function queueKeyAction(mode, key, { metaKey = false, ctrlKey = false } = {}) {
  if (metaKey || ctrlKey) return null;
  const map = QUEUE_KEYS[mode];
  if (!map) return null;
  return map[key] ?? null;
}
