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

export const BRIEF_MAX_LINES = 3;

/** Panel rows: at most three facts. "Could not load everything" is a notice, not a fact. */
export function briefRows(brief) {
  const notice = clean(brief?.notice);
  const rows = [];
  const text = clean(brief?.text);
  if (text && text !== notice) rows.push({ text, playbook: false });
  for (const line of brief?.lines || []) {
    const lineText = clean(line?.text);
    if (lineText) rows.push({ text: lineText, playbook: line.source === "playbook" });
  }
  return { notice, rows: rows.slice(0, BRIEF_MAX_LINES), label: clean(brief?.label) };
}

/** What the contact panel paints for the selected contact. Only that contact's read, never the previous one. */
export function panelBrief({ contactId, cache, flightContactId, failedContactId = null }) {
  const empty = { notice: null, rows: [], label: null };
  if (!contactId) return { state: "none", ...empty };
  const brief = briefForContact(contactId, cache);
  if (brief) return { state: "ready", ...briefRows(brief) };
  if (flightContactId === contactId) return { state: "loading", ...empty };
  if (failedContactId === contactId) return { state: "failed", ...empty };
  return { state: "none", ...empty };
}

function clean(value) {
  const text = typeof value === "string" ? value.trim() : "";
  return text || null;
}

export function briefRequest(contactId, connectionId) {
  const params = new URLSearchParams({
    contact_id: contactId,
    connection_id: connectionId || "hubspot",
  });
  return `/briefs?${params.toString()}`;
}
