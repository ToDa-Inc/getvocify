/** One-line say-this copy for the live-assist card (max 90 chars). */
export function formatCopilotSayThisLine(text, maxLen = 90) {
  const oneLine = String(text ?? '').replace(/\s+/g, ' ').trim();
  if (!oneLine) return '';
  if (oneLine.length <= maxLen) return oneLine;
  return `${oneLine.slice(0, maxLen - 1).trimEnd()}…`;
}
