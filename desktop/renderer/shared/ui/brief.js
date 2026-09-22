// The pre-call list. Empty labels are not rows.

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

export function briefRequest(contactId, connectionId) {
  const params = new URLSearchParams({
    contact_id: contactId,
    connection_id: connectionId || "hubspot",
  });
  return `/briefs?${params.toString()}`;
}
