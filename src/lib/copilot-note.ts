const NEXT_STEPS_HEADING = /^(próximos\s+pasos|next\s+steps)$/i;

function isHeading(line: string) {
  return /^#{1,3}\s+\S/.test(line);
}

function headingTitle(line: string) {
  return line.replace(/^#{1,3}\s+/, "").trim();
}

function isNestedListItem(line: string) {
  return /^\s{2,}[-*+]\s+/.test(line);
}

function isListItem(line: string) {
  return /^\s*[-*+]\s+/.test(line);
}

function stripListMarker(line: string) {
  return line.replace(/^\s*[-*+]\s+/, "").trim();
}

export function stripNextStepsSection(markdown: string) {
  const lines = String(markdown || "").split(/\r?\n/);
  let cut = -1;
  for (let i = 0; i < lines.length; i += 1) {
    if (isHeading(lines[i]) && NEXT_STEPS_HEADING.test(headingTitle(lines[i]))) {
      cut = i;
      break;
    }
  }
  if (cut < 0) return String(markdown || "").trim();
  return lines.slice(0, cut).join("\n").trim();
}

function escapeHtml(s: string) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineHtml(text: string) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

export function renderCopilotNoteHtml(markdown: string) {
  const lines = String(stripNextStepsSection(markdown) || "").split(/\r?\n/);
  const sections: { title: string; items: { text: string; children: string[] }[] }[] = [];
  let current: (typeof sections)[number] | null = null;
  let lastItem: { text: string; children: string[] } | null = null;

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (isHeading(line)) {
      current = { title: headingTitle(line), items: [] };
      lastItem = null;
      sections.push(current);
      continue;
    }
    const nested = isNestedListItem(line);
    const bullet = isListItem(line);
    if (!current) {
      current = { title: "", items: [] };
      sections.push(current);
    }
    if (!bullet) {
      lastItem = { text: line.trim(), children: [] };
      current.items.push(lastItem);
      continue;
    }
    const text = stripListMarker(line);
    if (nested && lastItem) {
      lastItem.children.push(text);
    } else {
      lastItem = { text, children: [] };
      current.items.push(lastItem);
    }
  }

  const hasHeadings = sections.some((s) => s.title);
  if (!hasHeadings) {
    const text = String(markdown || "").trim();
    if (!text) return "";
    return text
      .split(/\n{2,}/)
      .map((p) => `<p>${inlineHtml(p.trim())}</p>`)
      .join("");
  }

  return sections
    .map((section) => {
      const heading = section.title ? `<h3>${inlineHtml(section.title)}</h3>` : "";
      if (!section.items.length) return heading;
      const lis = section.items.map((item) => {
        const kids = item.children.length
          ? `<ul>${item.children.map((c) => `<li>${inlineHtml(c)}</li>`).join("")}</ul>`
          : "";
        return `<li>${inlineHtml(item.text)}${kids}</li>`;
      });
      return `${heading}<ul>${lis.join("")}</ul>`;
    })
    .join("");
}

export function memoContactName(memo: { extraction?: { contactName?: string | null; companyName?: string | null } | null } | null) {
  return String(memo?.extraction?.contactName || "").trim();
}

export function memoListTitle(memo: { extraction?: { contactName?: string | null; companyName?: string | null } | null } | null) {
  return memoContactName(memo) || String(memo?.extraction?.companyName || "").trim() || "Untitled conversation";
}

export function memoListSubtitle(memo: { extraction?: { contactName?: string | null; companyName?: string | null } | null } | null) {
  const contact = memoContactName(memo);
  const company = String(memo?.extraction?.companyName || "").trim();
  if (contact && company && company.toLowerCase() !== contact.toLowerCase()) return company;
  return "";
}
