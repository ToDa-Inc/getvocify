/**
 * SSE parser for POST /api/v1/copilot/suggest.
 * Same framing as src/features/copilot/api/suggest.ts.
 */

export const PRODUCT_CONTEXT_STORAGE_KEY = 'vocify_copilot_product_context';

export const DEFAULT_PRODUCT_CONTEXT = `Product: Vocify — AI voice memos that extract CRM fields and sync to HubSpot after sales calls.
Ideal customer: B2B sales teams / founders who hate typing notes into CRM after calls.
Pain: Lost deal context, delayed CRM hygiene, reps avoid logging calls.
Value: Speak after (or during) the call → structured fields → push to CRM in seconds.
Proof angles: Speeds CRM updates, reduces forgotten follow-ups, keeps pipeline trustworthy.
Tone: Direct, founder-to-founder, no fluff. Spanish or English OK.`;

export function parseSseBuffer(buffer) {
  const parts = String(buffer || '').split('\n\n');
  const rest = parts.pop() || '';
  const events = [];

  for (const part of parts) {
    const line = part
      .split('\n')
      .map((l) => l.trim())
      .find((l) => l.startsWith('data:'));
    if (!line) continue;
    const raw = line.slice(5).trim();
    if (!raw) continue;
    try {
      events.push(JSON.parse(raw));
    } catch {
      /* ignore partial / malformed JSON */
    }
  }

  return { events, rest };
}
