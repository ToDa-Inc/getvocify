/** Pure state for the demo buyer window: conversation history plus what the seller has said since the last buyer turn. */

export const REPLY_QUIET_MS = 1400;

export function createDemoSession() {
  return { history: [], pendingSeller: [] };
}

export function addSellerText(session, text) {
  const clean = String(text || '').trim();
  if (clean) session.pendingSeller.push(clean);
  return session;
}

export function hasPendingSeller(session) {
  return session.pendingSeller.length > 0;
}

/** Moves the pending seller speech into the history and returns it as one string ('' when nothing is pending). */
export function takeSellerTurn(session) {
  if (!session.pendingSeller.length) return '';
  const text = session.pendingSeller.join(' ');
  session.pendingSeller = [];
  session.history.push({ role: 'seller', text });
  return text;
}

export function addBuyerLine(session, text) {
  const clean = String(text || '').trim();
  if (clean) session.history.push({ role: 'buyer', text: clean });
  return session;
}

/** History sent with a free reply: everything before the seller turn that is sent as `seller_text`. */
export function historyBeforeLastSeller(session) {
  const last = session.history.length - 1;
  return last >= 0 && session.history[last].role === 'seller' ? session.history.slice(0, last) : [...session.history];
}

export function base64ToArrayBuffer(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}
