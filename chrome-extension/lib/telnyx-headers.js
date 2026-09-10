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

export function telnyxHangupMessage(call) {
  const sip = Number(call?.sipCode);
  const q850 = Number(call?.causeCode);
  const cause = [call?.cause, call?.hangupCause, call?.sipReason]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  if (sip === 486 || q850 === 17 || cause.includes('busy')) return 'Ocupado';
  if (
    sip === 480 ||
    sip === 408 ||
    q850 === 18 ||
    q850 === 19 ||
    cause.includes('timeout') ||
    cause.includes('no_answer') ||
    cause.includes('no answer')
  ) {
    return 'Sin respuesta';
  }
  if (sip === 603 || sip === 487 || cause.includes('reject')) return 'Llamada rechazada';
  return null;
}
