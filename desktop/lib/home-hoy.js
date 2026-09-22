/** Desktop home Hoy: same cards as the dialer, hidden while listening. */

export function todayItemToCard(item) {
  return {
    id: item.id,
    reason: item.reason,
    status: item.status ?? 'pending',
    version: item.version,
    undoDeadline: item.undo_deadline ?? null,
  };
}

function undoable(item, nowMs) {
  return item.status === 'dismissed' && item.undo_deadline != null && Date.parse(item.undo_deadline) >= nowMs;
}

/** Merge server items with local dismiss/undo overlays (mirrors web cardsAfterDismiss). */
export function homeHoyListedItems(serverItems, actedItems, nowMs) {
  const server = serverItems ?? [];
  const acted = actedItems ?? [];
  const actedById = new Map(acted.filter((item) => item.id).map((item) => [item.id, item]));
  const merged = server.map((item) => {
    const next = item.id ? actedById.get(item.id) : undefined;
    return next && undoable(next, nowMs) ? next : item;
  });
  const serverIds = new Set(server.map((item) => item.id).filter(Boolean));
  const extra = acted.filter((item) => item.id && !serverIds.has(item.id) && undoable(item, nowMs));
  return [...merged, ...extra];
}

/** Cards to paint on the home surface. Listening always yields none. */
export function homeHoyCardsForDisplay({ captureActive, cards }) {
  if (captureActive) return [];
  return cards ?? [];
}

export function shouldFetchHomeHoy({ token, captureActive, inFlight, stale }) {
  if (!token || captureActive || inFlight || !stale) return false;
  return true;
}

export function homeHoyRequestPath() {
  return '/today';
}
