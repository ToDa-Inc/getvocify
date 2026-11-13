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

type NoteItem = { text: string; bullet: boolean; children: string[] };

/** `**Resultado:** how the call ended`: the note's first line, set apart from the facts under it. */
const LEAD_LINE = /^\*\*([^*:]{1,24}):\*\*\s*(\S.*)$/;

function itemsHtml(items: NoteItem[]) {
  let html = "";
  let list: string[] = [];
  const closeList = () => {
    if (list.length) html += `<ul>${list.join("")}</ul>`;
    list = [];
  };
  for (const item of items) {
    if (!item.bullet) {
      closeList();
      html += `<p>${inlineHtml(item.text)}</p>`;
      continue;
    }
    const kids = item.children.length
      ? `<ul>${item.children.map((c) => `<li>${inlineHtml(c)}</li>`).join("")}</ul>`
      : "";
    list.push(`<li>${inlineHtml(item.text)}${kids}</li>`);
  }
  closeList();
  return html;
}

export function renderCopilotNoteHtml(markdown: string) {
  const lines = String(stripNextStepsSection(markdown) || "").split(/\r?\n/);
  const sections: { title: string; items: NoteItem[] }[] = [];
  let current: (typeof sections)[number] | null = null;
  let lastItem: NoteItem | null = null;
  let lead = "";

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (isHeading(line)) {
      current = { title: headingTitle(line), items: [] };
      lastItem = null;
      sections.push(current);
      continue;
    }
    if (!current) {
      const match = lead ? null : LEAD_LINE.exec(line.trim());
      if (match) {
        lead = `<p data-note-lead><span>${escapeHtml(match[1])}</span>${inlineHtml(match[2])}</p>`;
        continue;
      }
      current = { title: "", items: [] };
      sections.push(current);
    }
    if (!isListItem(line)) {
      lastItem = { text: line.trim(), bullet: false, children: [] };
      current.items.push(lastItem);
      continue;
    }
    const text = stripListMarker(line);
    if (isNestedListItem(line) && lastItem) {
      lastItem.children.push(text);
    } else {
      lastItem = { text, bullet: true, children: [] };
      current.items.push(lastItem);
    }
  }

  return (
    lead +
    sections
      .map((section) => (section.title ? `<h3>${inlineHtml(section.title)}</h3>` : "") + itemsHtml(section.items))
      .join("")
  );
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

const GENERIC_RECORDING_TITLE = /^(call|llamada vocify)$/i;

export function isGenericRecordingTitle(title?: string | null): boolean {
  const trimmed = (title || "").trim();
  return !trimmed || GENERIC_RECORDING_TITLE.test(trimmed);
}

export function recordingListTitle(
  recording: {
    title?: string | null;
    to_number?: string | null;
    from_number?: string | null;
  },
  memo?: Parameters<typeof memoListTitle>[0] | null,
  formatPhone?: (e164: string) => string,
): string {
  const hubspotTitle = (recording.title || "").trim();
  if (hubspotTitle && !isGenericRecordingTitle(hubspotTitle)) {
    return hubspotTitle;
  }
  if (memo) {
    const fromMemo = memoListTitle(memo);
    if (fromMemo && fromMemo !== "Untitled conversation") {
      return fromMemo;
    }
  }
  const phone = (recording.to_number || recording.from_number || "").trim();
  if (phone) {
    return formatPhone ? formatPhone(phone) || phone : phone;
  }
  return hubspotTitle || "Call";
}
