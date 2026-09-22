// Presentation only. Does not rewrite the transcript that gets persisted.
export function reconcileTranscript(previous, incoming) {
  if (previous == null) return incoming;
  if (incoming == null) return previous;
  const prevRev = Number(previous.revision ?? 0);
  const nextRev = Number(incoming.revision ?? 0);
  if (nextRev < prevRev) return previous;
  const turns = incoming.turns ?? [];
  const ids = new Set(turns.map((turn) => turn.id));
  const interim = incoming.interim && ids.has(incoming.interim.id) ? null : incoming.interim ?? null;
  return { ...incoming, turns, interim };
}

export function scrollFollow({ scrollTop = 0, scrollHeight = 0, clientHeight = 0, threshold = 32 } = {}) {
  const distance = scrollHeight - clientHeight - scrollTop;
  const follow = distance <= threshold;
  return { follow, showReturnToLive: !follow, label: 'Volver al directo' };
}
