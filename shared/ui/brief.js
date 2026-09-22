// The pre-call list. Empty labels are not rows.

export function visibleBrief(brief) {
  const lines = [];
  if (brief.text) lines.push(brief.text);
  for (const line of brief.lines || []) {
    if (line.text) lines.push(line.text);
  }
  return lines;
}
