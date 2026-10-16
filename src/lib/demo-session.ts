/** Pure state for the demo buyer: the conversation so far and what the seller said since the buyer last spoke. */

export const REPLY_QUIET_MS = 1400;
/** The buyer's own voice reaches the mic a moment after it stops: ignore the seller's speech until then. */
export const ECHO_GUARD_MS = 1200;

export type DemoRole = "buyer" | "seller";
export type DemoTurn = { role: DemoRole; text: string };
export type DemoSession = { history: DemoTurn[]; pendingSeller: string[] };

export function createDemoSession(): DemoSession {
  return { history: [], pendingSeller: [] };
}

export function addSellerText(session: DemoSession, text: string): void {
  const clean = text.trim();
  if (clean) session.pendingSeller.push(clean);
}

export function hasPendingSeller(session: DemoSession): boolean {
  return session.pendingSeller.length > 0;
}

/** Moves the pending seller speech into the history and returns it as one string ('' when nothing is pending). */
export function takeSellerTurn(session: DemoSession): string {
  if (!session.pendingSeller.length) return "";
  const text = session.pendingSeller.join(" ");
  session.pendingSeller = [];
  session.history.push({ role: "seller", text });
  return text;
}

export function addBuyerLine(session: DemoSession, text: string): void {
  const clean = text.trim();
  if (clean) session.history.push({ role: "buyer", text: clean });
}

/** The history sent with a free reply: everything before the seller turn that goes as `seller_text`. */
export function historyBeforeLastSeller(session: DemoSession): DemoTurn[] {
  const last = session.history.length - 1;
  return last >= 0 && session.history[last].role === "seller" ? session.history.slice(0, last) : [...session.history];
}

export function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}
