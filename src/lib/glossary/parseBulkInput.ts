/**
 * Parse bulk glossary input from paste or file (CSV/TXT).
 * Supports: one word per line, comma-separated, or CSV with headers.
 */

export interface ParsedBulkItem {
  word: string;
  category: string;
  hints: string[];
}

const HEADER_PATTERNS = [
  /^word\b/i,
  /^target_word\b/i,
  /^term\b/i,
];

function splitCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') {
      inQuotes = !inQuotes;
    } else if (c === "," && !inQuotes) {
      result.push(current.trim());
      current = "";
    } else {
      current += c;
    }
  }
  result.push(current.trim());
  return result;
}

function isHeaderLine(firstCell: string): boolean {
  return HEADER_PATTERNS.some((p) => p.test(firstCell));
}

const CATEGORIES = ["Company", "Competitor", "Product", "Technical", "General", "Slang"];

function isValidCategory(s: string): boolean {
  return CATEGORIES.includes(s.trim());
}

export function parseBulkInput(
  text: string,
  defaultCategory: string = "General",
): ParsedBulkItem[] {
  const lines = text
    .split(/[\r\n]+/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];

  const seen = new Set<string>();
  const result: ParsedBulkItem[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const parts = splitCSVLine(line).map((p) => p.replace(/^"|"$/g, "").trim()).filter(Boolean);

    if (parts.length === 0) continue;

    const first = parts[0] ?? "";
    if (!first) continue;

    if (i === 0 && isHeaderLine(first)) continue;

    const secondIsCategory = parts.length >= 2 && isValidCategory(parts[1] ?? "");
    const isStructured = parts.length >= 3 || (parts.length === 2 && secondIsCategory);

    if (isStructured) {
      const word = first;
      if (!seen.has(word)) {
        seen.add(word);
        const category = secondIsCategory ? (parts[1] ?? defaultCategory) : defaultCategory;
        const hintsStr = parts.length >= 3 ? parts.slice(2).join(",") : "";
        const hints = hintsStr
          ? hintsStr.split(/[|,;]/).map((h) => h.trim()).filter(Boolean)
          : [];
        result.push({ word, category, hints });
      }
    } else {
      for (const part of parts) {
        const word = part.trim();
        if (word && !seen.has(word)) {
          seen.add(word);
          result.push({ word, category: defaultCategory, hints: [] });
        }
      }
    }
  }

  return result;
}
