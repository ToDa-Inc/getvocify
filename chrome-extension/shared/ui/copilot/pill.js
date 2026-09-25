export const PILL_MIN_HOLD_MS = 4000;
export const PILL_MAX_SHOW_MS = 10000;
export const PILL_CATEGORY_COOLDOWN_MS = 60000;

export function initialPillState() {
  return { meetingId: null, visible: null, lastShownAt: {} };
}

/** One line, trimmed, max 90 characters. */
export function formatPillText(raw) {
  const oneLine = String(raw ?? "").replace(/\s+/g, " ").trim();
  if (!oneLine) return "";
  return oneLine.length > 90 ? oneLine.slice(0, 90) : oneLine;
}

function pillCategory(value) {
  const trimmed = value == null ? "" : String(value).trim();
  return trimmed || "none";
}

/**
 * Pure visibility/timing decision for the live help line.
 * @returns {{ show: boolean, text?: string, state: ReturnType<typeof initialPillState> }}
 */
export function pillDecision(state, input, now) {
  const base = state ?? initialPillState();
  let next = { ...base, lastShownAt: { ...base.lastShownAt } };
  const meetingId = input?.meetingId ?? null;

  if (meetingId != null && meetingId !== next.meetingId) {
    next = { meetingId, visible: null, lastShownAt: {} };
  } else if (meetingId != null) {
    next.meetingId = meetingId;
  }

  if (next.visible && now - next.visible.shownAt >= PILL_MAX_SHOW_MS) {
    next = { ...next, visible: null };
  }

  const blocked =
    input?.kind !== "meeting" ||
    input?.enabled !== true ||
    input?.speakerRole === "rep";

  if (next.visible && !blocked && now - next.visible.shownAt < PILL_MAX_SHOW_MS) {
    return { show: true, text: next.visible.text, state: next };
  }

  if (blocked) {
    return { show: false, state: next };
  }

  const text = formatPillText(input?.text);
  if (!text) {
    return { show: false, state: next };
  }

  const category = pillCategory(input?.category);
  const lastAt = next.lastShownAt[category] ?? -Infinity;
  if (now - lastAt < PILL_CATEGORY_COOLDOWN_MS) {
    return { show: false, state: next };
  }

  if (next.visible && now - next.visible.shownAt < PILL_MIN_HOLD_MS) {
    return { show: true, text: next.visible.text, state: next };
  }

  next = {
    ...next,
    visible: { text, category, shownAt: now },
    lastShownAt: { ...next.lastShownAt, [category]: now },
  };
  return { show: true, text, state: next };
}
