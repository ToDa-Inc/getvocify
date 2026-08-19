/**
 * Tiny Granola-style note parser for the extension review screen.
 * Supports # headings, - bullets, one nested level, and **bold**.
 */

const NEXT_STEPS_HEADING = /^(próximos\s+pasos|next\s+steps)$/i;

function looksSpanish(text) {
  const t = String(text || '').toLowerCase();
  if (/[áéíóúñ¿¡]/.test(t)) return true;
  const cues = ['hola', 'gracias', 'nosotros', 'llamada', 'próxim', 'proxim', 'sí', 'que tal'];
  return cues.filter((c) => t.includes(c)).length >= 2;
}

export function nextStepsHeadingLabel(markdown) {
  return looksSpanish(markdown) ? 'Próximos pasos' : 'Next steps';
}

export function crmFieldsHeadingLabel(_markdown) {
  return 'Fields';
}

function isHeading(line) {
  return /^#{1,3}\s+\S/.test(line);
}

function headingTitle(line) {
  return line.replace(/^#{1,3}\s+/, '').trim();
}

function isNestedListItem(line) {
  return /^\s{2,}[-*+]\s+/.test(line);
}

function isListItem(line) {
  return /^\s*[-*+]\s+/.test(line);
}

function stripListMarker(line) {
  return line.replace(/^\s*[-*+]\s+/, '').trim();
}

export function stripNextStepsSection(markdown) {
  const lines = String(markdown || '').split(/\r?\n/);
  let cut = -1;
  for (let i = 0; i < lines.length; i += 1) {
    if (isHeading(lines[i]) && NEXT_STEPS_HEADING.test(headingTitle(lines[i]))) {
      cut = i;
      break;
    }
  }
  if (cut < 0) return String(markdown || '').trim();
  return lines.slice(0, cut).join('\n').trim();
}

export function parseCopilotNote(markdown) {
  const lines = String(markdown || '').split(/\r?\n/);
  const sections = [];
  let current = null;
  let lastItem = null;

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) continue;
    if (isHeading(line)) {
      current = { title: headingTitle(line), items: [] };
      lastItem = null;
      sections.push(current);
      continue;
    }
    const nested = isNestedListItem(line);
    const bullet = isListItem(line);
    if (!bullet) {
      if (!current) {
        current = { title: '', items: [] };
        sections.push(current);
      }
      current.items.push({ text: line.trim(), children: [] });
      lastItem = current.items[current.items.length - 1];
      continue;
    }
    if (!current) {
      current = { title: '', items: [] };
      sections.push(current);
    }
    const text = stripListMarker(line);
    if (nested && lastItem) {
      lastItem.children.push(text);
    } else {
      lastItem = { text, children: [] };
      current.items.push(lastItem);
    }
  }

  return { sections };
}

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function inlineHtml(text) {
  const escaped = escapeHtml(text);
  return escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

function itemsToList(items) {
  if (!items.length) return '';
  const lis = items.map((item) => {
    const kids = item.children?.length
      ? `<ul>${item.children.map((c) => `<li>${inlineHtml(c)}</li>`).join('')}</ul>`
      : '';
    return `<li>${inlineHtml(item.text)}${kids}</li>`;
  });
  return `<ul>${lis.join('')}</ul>`;
}

export function renderCopilotNoteHtml(markdown) {
  const parsed = parseCopilotNote(stripNextStepsSection(markdown));
  const hasHeadings = parsed.sections.some((s) => s.title);
  if (!hasHeadings) {
    const text = String(markdown || '').trim();
    if (!text) return '';
    return text
      .split(/\n{2,}/)
      .map((p) => `<p>${inlineHtml(p.trim())}</p>`)
      .join('');
  }
  return parsed.sections.map((section) => {
    const heading = section.title ? `<h3>${inlineHtml(section.title)}</h3>` : '';
    return `${heading}${itemsToList(section.items)}`;
  }).join('');
}

function decodeEntities(text) {
  return String(text ?? '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function extractUntilClose(src, from, tag) {
  const openRe = new RegExp(`<${tag}(\\s[^>]*)?>`, 'gi');
  const closeRe = new RegExp(`</${tag}>`, 'gi');
  let depth = 1;
  let i = from;
  while (i < src.length && depth > 0) {
    openRe.lastIndex = i;
    closeRe.lastIndex = i;
    const open = openRe.exec(src);
    const close = closeRe.exec(src);
    const openAt = open ? open.index : Infinity;
    const closeAt = close ? close.index : Infinity;
    if (closeAt === Infinity && openAt === Infinity) break;
    if (openAt < closeAt) {
      depth += 1;
      i = openAt + open[0].length;
    } else {
      depth -= 1;
      if (depth === 0) {
        return { inner: src.slice(from, closeAt), end: closeAt + close[0].length };
      }
      i = closeAt + close[0].length;
    }
  }
  return { inner: src.slice(from), end: src.length };
}

function topLevelTags(html, tag) {
  const src = String(html || '');
  const out = [];
  const openRe = new RegExp(`<${tag}(\\s[^>]*)?>`, 'gi');
  let i = 0;
  while (i < src.length) {
    openRe.lastIndex = i;
    const open = openRe.exec(src);
    if (!open) break;
    const extracted = extractUntilClose(src, open.index + open[0].length, tag);
    out.push(extracted.inner);
    i = extracted.end;
  }
  return out;
}

function inlineToMd(html) {
  let s = String(html || '');
  s = s.replace(/<br\s*\/?>/gi, ' ');
  s = s.replace(/<\/?(strong|b)[^>]*>/gi, '**');
  s = s.replace(/<[^>]+>/g, '');
  return decodeEntities(s).replace(/\s+/g, ' ').trim();
}

function listToMd(ulInner, indent = 0) {
  const pad = ' '.repeat(indent);
  const lines = [];
  for (const li of topLevelTags(ulInner, 'li')) {
    const nestedUls = topLevelTags(li, 'ul');
    let withoutNested = li;
    for (const nested of nestedUls) {
      withoutNested = withoutNested.replace(`<ul>${nested}</ul>`, '');
      withoutNested = withoutNested.replace(new RegExp(`<ul[^>]*>${nested.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}</ul>`, 'i'), '');
    }
    withoutNested = withoutNested.replace(/<ul[\s\S]*?<\/ul>/gi, '');
    const text = inlineToMd(withoutNested);
    if (text) lines.push(`${pad}- ${text}`);
    for (const nested of nestedUls) {
      lines.push(...listToMd(nested, indent + 2));
    }
  }
  return lines;
}

export function htmlToCopilotMarkdown(html) {
  const src = String(html || '').trim();
  if (!src) return '';
  const lines = [];
  let i = 0;
  while (i < src.length) {
    const slice = src.slice(i);
    const open = slice.match(/^<(h3|ul|ol|p|div)(\s[^>]*)?>/i);
    if (open) {
      const tag = open[1].toLowerCase();
      const extracted = extractUntilClose(src, i + open[0].length, tag);
      if (tag === 'h3') {
        const title = inlineToMd(extracted.inner);
        if (title) lines.push(`# ${title}`);
      } else if (tag === 'ul' || tag === 'ol') {
        lines.push(...listToMd(extracted.inner, 0));
      } else {
        const nested = htmlToCopilotMarkdown(extracted.inner);
        if (nested) lines.push(nested);
        else {
          const text = inlineToMd(extracted.inner);
          if (text) lines.push(text);
        }
      }
      i = extracted.end;
      continue;
    }
    if (slice.startsWith('<')) {
      const close = slice.indexOf('>');
      i += close >= 0 ? close + 1 : 1;
      continue;
    }
    const nextTag = src.indexOf('<', i);
    const text = inlineToMd(src.slice(i, nextTag < 0 ? src.length : nextTag));
    if (text) lines.push(text);
    i = nextTag < 0 ? src.length : nextTag;
  }
  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}
