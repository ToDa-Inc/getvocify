import { strings } from '../renderer/shared/ui/i18n.js';

const UI_LOCALES = ['es', 'en'];

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Speaker labels from every UI locale in the i18n catalog. */
export function catalogSpeakerLabels() {
  const you = new Set();
  const them = new Set();
  for (const code of UI_LOCALES) {
    const t = strings({ vocify_lang: code });
    you.add(t.speakerYou);
    them.add(t.speakerThem);
  }
  return { you: [...you], them: [...them] };
}

export function speakerSplitPattern() {
  const { you, them } = catalogSpeakerLabels();
  const all = [...you, ...them].map(escapeRegExp).join('|');
  return new RegExp(`(?=(?:${all}): )`);
}

export function splitTaggedTranscript(text) {
  const trimmed = `${text ?? ''}`.trim();
  if (!trimmed) return [];
  return trimmed.split(speakerSplitPattern()).filter(Boolean);
}

/** @returns {'rep' | 'prospect' | null} */
export function turnRoleFromPart(part) {
  const { you, them } = catalogSpeakerLabels();
  for (const label of you) {
    if (part.startsWith(`${label}:`)) return 'rep';
  }
  for (const label of them) {
    if (part.startsWith(`${label}:`)) return 'prospect';
  }
  return null;
}

export function stripSpeakerPrefix(part) {
  const { you, them } = catalogSpeakerLabels();
  const labels = [...you, ...them].sort((a, b) => b.length - a.length);
  for (const label of labels) {
    const withSpace = `${label}: `;
    if (part.startsWith(withSpace)) return part.slice(withSpace.length);
    const bare = `${label}:`;
    if (part.startsWith(bare)) return part.slice(bare.length).replace(/^\s*/, '');
  }
  return part;
}

/** Adjacent chunks from the same speaker are one paragraph, not a new bubble. */
export function coalesceSpeakerParts(parts) {
  const out = [];
  for (const part of parts) {
    const role = turnRoleFromPart(part);
    const prev = out[out.length - 1];
    if (role && prev && turnRoleFromPart(prev) === role) {
      const body = `${stripSpeakerPrefix(prev)} ${stripSpeakerPrefix(part)}`.replace(/\s+/g, ' ').trim();
      const label = part.slice(0, part.indexOf(':'));
      out[out.length - 1] = `${label}: ${body}`;
    } else {
      out.push(part);
    }
  }
  return out;
}

export function latestTaggedTurnBody(finalTranscript) {
  const parts = splitTaggedTranscript(finalTranscript);
  const last = parts[parts.length - 1];
  if (!last) return '';
  return stripSpeakerPrefix(last).trim();
}

/** Role of a single tagged transcript line (overlay pill gating). */
export function speakerRoleFromLastLine(lastLine) {
  const line = String(lastLine ?? '').trim();
  if (!line) return null;
  return turnRoleFromPart(line);
}
