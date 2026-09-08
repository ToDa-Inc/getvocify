/**
 * SIP custom headers for Telnyx parked WebRTC legs.
 * Correlation only — the server resolve_caller_id is the From authority.
 */

export function vocifyCallHeaders({ callerId, contactId, dealId }) {
  const headers = [];
  if (callerId) headers.push({ name: 'X-Vocify-Caller-Id', value: String(callerId) });
  if (contactId) headers.push({ name: 'X-Vocify-Contact-Id', value: String(contactId) });
  if (dealId) headers.push({ name: 'X-Vocify-Deal-Id', value: String(dealId) });
  return headers;
}
