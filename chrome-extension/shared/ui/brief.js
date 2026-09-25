// The pre-call list. Empty labels are not rows.

/** Same string as `productCatalog.es.teamLoading`. */
export const BRIEF_LOADING = "Leyendo…";
export const BRIEF_EMPTY = "Nada pendiente en esta ficha.";

export function visibleBrief(brief) {
  const lines = [];
  if (brief.text) lines.push(brief.text);
  for (const line of brief.lines || []) {
    if (line.text) lines.push(line.text);
  }
  return lines;
}

export function briefForContact(contactId, cached) {
  if (!contactId || !cached || cached.contactId !== contactId) return null;
  return cached.brief;
}

export function briefOnContact({ objectType, captureActive, brief }) {
  if (captureActive || objectType !== "contact" || !brief) return [];
  return visibleBrief(brief);
}

/** One loading line for the active fetch; never reuse another contact's brief. */
export function contactBriefDisplayLines({
  objectType,
  contactId,
  captureActive,
  cache,
  flightContactId,
}) {
  if (!contactId || captureActive || objectType !== "contact") return [];
  const brief = briefForContact(contactId, cache);
  const lines = briefOnContact({ objectType: "contact", captureActive: false, brief });
  if (lines.length) return lines;
  if (flightContactId === contactId) return [BRIEF_LOADING];
  if (brief) return [BRIEF_EMPTY];
  return [];
}

export function shouldApplyBriefResponse(flightContactId, responseContactId) {
  return Boolean(flightContactId) && flightContactId === responseContactId;
}

export function briefRequest(contactId, connectionId) {
  const params = new URLSearchParams({
    contact_id: contactId,
    connection_id: connectionId || "hubspot",
  });
  return `/briefs?${params.toString()}`;
}
