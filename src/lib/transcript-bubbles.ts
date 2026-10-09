/** Target bubble length; a single long sentence is never split. */
const BUBBLE_CHARS = 220;

/** Sentence-ish pieces that keep their closing punctuation (., ?, !, …). */
function sentences(text: string): string[] {
  const parts = text.match(/[^.!?…]+(?:[.!?…]+["'”»)]*|$)/g) ?? [text];
  return parts.map((p) => p.trim()).filter(Boolean);
}

/**
 * Splits one speaker's paragraph into chat bubbles at sentence boundaries, the
 * way people actually talk in turns. Short replies stay one bubble.
 */
export function bubblesForTurn(text: string, maxChars = BUBBLE_CHARS): string[] {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return [];
  if (clean.length <= maxChars) return [clean];
  const bubbles: string[] = [];
  let current = "";
  for (const sentence of sentences(clean)) {
    if (current && current.length + 1 + sentence.length > maxChars) {
      bubbles.push(current);
      current = sentence;
    } else {
      current = current ? `${current} ${sentence}` : sentence;
    }
  }
  if (current) bubbles.push(current);
  return bubbles;
}
