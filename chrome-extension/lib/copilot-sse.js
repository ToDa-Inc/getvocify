/**
 * SSE parser for POST /api/v1/copilot/suggest.
 * Same framing as src/features/copilot/api/suggest.ts.
 */

export const PRODUCT_CONTEXT_STORAGE_KEY = 'vocify_copilot_product_context';

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
