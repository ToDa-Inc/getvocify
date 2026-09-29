export type Inline =
  | { t: "text"; v: string }
  | { t: "bold"; v: string }
  | { t: "code"; v: string }
  | { t: "cite"; n: number }
  | { t: "link"; label: string; href: string };

export type Block =
  | { t: "p"; inline: Inline[] }
  | { t: "ul"; items: Inline[][] }
  | { t: "ol"; items: Inline[][] }
  | { t: "table"; head: Inline[][]; rows: Inline[][][] };

const TOKEN = /\*\*([^*]+)\*\*|`([^`]+)`|\[(\d{1,2})\]|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;

/** Bold, code, numbered citations and http(s) links. Everything else is plain text; nothing becomes HTML. */
export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of text.matchAll(TOKEN)) {
    if (m.index > last) out.push({ t: "text", v: text.slice(last, m.index) });
    if (m[1] !== undefined) out.push({ t: "bold", v: m[1] });
    else if (m[2] !== undefined) out.push({ t: "code", v: m[2] });
    else if (m[3] !== undefined) out.push({ t: "cite", n: Number(m[3]) });
    else out.push({ t: "link", label: m[4], href: m[5] });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ t: "text", v: text.slice(last) });
  return out;
}

const BULLET = /^\s*[-*•]\s+(.*)$/;
const ORDERED = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^#{1,6}\s+(.*)$/;
const ROW = /^\s*\|.*\|\s*$/;
const RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function cells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

export function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (ROW.test(line) && i + 1 < lines.length && RULE.test(lines[i + 1])) {
      const head = cells(line).map(parseInline);
      i += 2;
      const rows: Inline[][][] = [];
      while (i < lines.length && ROW.test(lines[i])) rows.push(cells(lines[i++]).map(parseInline));
      blocks.push({ t: "table", head, rows });
      continue;
    }
    const kind = BULLET.test(line) ? "ul" : ORDERED.test(line) ? "ol" : null;
    if (kind) {
      const re = kind === "ul" ? BULLET : ORDERED;
      const items: Inline[][] = [];
      while (i < lines.length && re.test(lines[i])) items.push(parseInline(lines[i++].match(re)![1]));
      blocks.push({ t: kind, items });
      continue;
    }
    // The first line is always consumed, so a lone pipe row (no separator) is text, not a loop.
    const buf: string[] = [];
    do {
      const heading = lines[i].match(HEADING);
      buf.push(heading ? `**${heading[1]}**` : lines[i]);
      i++;
    } while (i < lines.length && lines[i].trim() && !BULLET.test(lines[i]) && !ORDERED.test(lines[i]) && !(ROW.test(lines[i]) && i + 1 < lines.length && RULE.test(lines[i + 1])));
    blocks.push({ t: "p", inline: parseInline(buf.join("\n")) });
  }
  return blocks;
}
