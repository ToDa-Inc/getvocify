// A human note. Blank text is not saved. The offset stays a number.

export function noteSaveBody(text, offsetMs) {
  const body = String(text || "").trim();
  if (!body) return null;
  const offset = Number.isFinite(offsetMs) && offsetMs >= 0 ? Math.round(offsetMs) : 0;
  return { text: body, offset_ms: offset };
}
