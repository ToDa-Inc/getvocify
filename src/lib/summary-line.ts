/** A memo summary as one line of prose: no markdown headings, bullets or emphasis. */
export function plainSummary(summary: string | null | undefined): string {
  const lines: string[] = [];
  for (const raw of String(summary ?? "").split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    lines.push(line.replace(/^([*\-•]|\d+[.)])\s+/, ""));
  }
  return lines.join(" ").replace(/\*\*|__/g, "").replace(/\s+/g, " ").trim();
}

/** An Ask answer as plain text: the dashboard has no markdown renderer, so keep the lines and drop the syntax. */
export function plainAnswer(answer: string | null | undefined): string {
  return String(answer ?? "")
    .split("\n")
    .map((raw) =>
      raw
        .trim()
        .replace(/^#+\s*/, "")
        .replace(/^[*\-•]\s+/, "· ")
        .replace(/\*\*|__/g, "")
        .replace(/🔗\s*(?=\[)/gu, ""),
    )
    .join("\n")
    .trim();
}

export type AnswerPart = { text: string; href?: string };

/** Splits `[label](https://…)` out of an answer so it renders as a real link. */
export function answerParts(answer: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  const link = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let last = 0;
  for (const match of answer.matchAll(link)) {
    const at = match.index ?? 0;
    if (at > last) parts.push({ text: answer.slice(last, at) });
    parts.push({ text: match[1], href: match[2] });
    last = at + match[0].length;
  }
  if (last < answer.length) parts.push({ text: answer.slice(last) });
  return parts;
}
