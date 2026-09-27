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
        .replace(/\*\*|__/g, ""),
    )
    .join("\n")
    .trim();
}
