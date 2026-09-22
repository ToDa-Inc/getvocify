// A human note. Blank text is not saved. The offset stays a number.

export function noteOffsetMsFromPlaybackSeconds(positionSeconds) {
  if (positionSeconds == null || !Number.isFinite(Number(positionSeconds)) || Number(positionSeconds) < 0) {
    return 0;
  }
  return Math.round(Number(positionSeconds) * 1000);
}

/** Current scrub position when review audio is loaded; otherwise 0. */
export function noteOffsetMsFromReviewAudio(audio) {
  if (!audio) return 0;
  const src = String(audio.currentSrc || audio.src || "").trim();
  if (!src) return 0;
  return noteOffsetMsFromPlaybackSeconds(audio.currentTime);
}

export function noteSaveBody(text, offsetMs) {
  const body = String(text || "").trim();
  if (!body) return null;
  const offset = Number.isFinite(offsetMs) && offsetMs >= 0 ? Math.round(offsetMs) : 0;
  return { text: body, offset_ms: offset };
}
