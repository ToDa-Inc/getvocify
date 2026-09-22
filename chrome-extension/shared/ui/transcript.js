// Presentation only. Does not rewrite the transcript that gets persisted.
export function reconcileTranscript(previous, incoming) {
  if (previous == null) return incoming;
  if (incoming == null) return previous;
  const prevRev = Number(previous.revision ?? 0);
  const nextRev = Number(incoming.revision ?? 0);
  if (nextRev < prevRev) return previous;
  return incoming;
}
