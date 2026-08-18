/**
 * Parse / normalize diarized transcripts for read-only review.
 */

const SPEAKER_LINE = /^(?:SPEAKER:\s*)?(S\d+|Speaker\s*\d+)\s*:?\s*$/i;
const SPEAKER_INLINE = /^(?:SPEAKER:\s*)?(S\d+|Speaker\s*\d+)\s*[:.-]\s*(.+)$/i;
const NAMED_SPEAKER_LINE = /^SPEAKER:\s*(?!S\d+\b)(.+?)\s*$/i;
const NAMED_SPEAKER_INLINE = /^SPEAKER:\s*(?!S\d+\b)([^:]+?)\s*[:.-]\s*(.+)$/i;

export function normalizeSpeaker(raw) {
  const m = String(raw || '').match(/(\d+)/);
  return m ? `S${m[1]}` : (raw ? String(raw).trim().toUpperCase() : null);
}

export function speakerSide(raw) {
  const s = normalizeSpeaker(raw);
  if (s === 'S1') return 's1';
  if (s === 'S2') return 's2';
  // Named diarization (JUAN) on a 2-party call sits with the prospect.
  if (s && !/^S\d+$/.test(s)) return 's2';
  return 'other';
}

export function speakerDisplayLabel(raw, labels = {}) {
  const side = speakerSide(raw);
  if (side === 's1') return labels.s1 || 'You';
  if (side === 's2') return labels.s2 || 'Them';
  return labels.s2 || raw || 'Speaker';
}

export function firstName(full) {
  const part = String(full || '').trim().split(/\s+/)[0];
  return part || '';
}

export function parseTranscriptTurns(text) {
  const raw = String(text || '').trim();
  if (!raw) return [];

  const turns = [];
  let current = null;

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (current) current.text += '\n';
      continue;
    }
    const inline = trimmed.match(SPEAKER_INLINE);
    if (inline) {
      if (current && current.text.trim()) turns.push(current);
      current = { speaker: inline[1].replace(/\s+/g, ''), text: inline[2].trim() };
      continue;
    }
    const onlySpeaker = trimmed.match(SPEAKER_LINE);
    if (onlySpeaker) {
      if (current && current.text.trim()) turns.push(current);
      current = { speaker: onlySpeaker[1].replace(/\s+/g, ''), text: '' };
      continue;
    }
    const namedInline = trimmed.match(NAMED_SPEAKER_INLINE);
    if (namedInline) {
      if (current && current.text.trim()) turns.push(current);
      current = { speaker: namedInline[1].trim(), text: namedInline[2].trim() };
      continue;
    }
    const namedOnly = trimmed.match(NAMED_SPEAKER_LINE);
    if (namedOnly) {
      if (current && current.text.trim()) turns.push(current);
      current = { speaker: namedOnly[1].trim(), text: '' };
      continue;
    }
    if (!current) current = { speaker: null, text: trimmed };
    else current.text = current.text ? `${current.text}\n${trimmed}` : trimmed;
  }
  if (current && current.text.trim()) turns.push(current);
  if (!turns.length && raw) return [{ speaker: null, text: raw }];
  return turns
    .map((t) => ({ speaker: t.speaker, text: t.text.replace(/\n+$/g, '').trim() }))
    .filter((t) => t.text);
}

function fingerprint(turn) {
  const speaker = normalizeSpeaker(turn.speaker) || '';
  const text = String(turn.text || '').replace(/\s+/g, ' ').trim().toLowerCase();
  return `${speaker}:${text.slice(0, 160)}`;
}

export function dedupeRepeatedConversation(turns) {
  if (!turns || turns.length < 4) return turns || [];
  const fps = turns.map(fingerprint);
  const n = turns.length;
  if (n % 2 === 0) {
    const mid = n / 2;
    if (fps.slice(0, mid).join('|') === fps.slice(mid).join('|')) {
      return turns.slice(0, mid);
    }
  }
  return turns;
}

export function mergeConsecutiveTurns(turns) {
  const out = [];
  for (const turn of turns || []) {
    const speaker = normalizeSpeaker(turn.speaker);
    const text = String(turn.text || '').trim();
    if (!text) continue;
    if (out.length && normalizeSpeaker(out[out.length - 1].speaker) === speaker) {
      out[out.length - 1].text = `${out[out.length - 1].text}\n${text}`;
    } else {
      out.push({ speaker, text });
    }
  }
  return out;
}

export function serializeTranscriptTurns(turns) {
  return (turns || [])
    .map((turn) => {
      const text = String(turn.text || '').trim();
      if (!text) return '';
      const speaker = normalizeSpeaker(turn.speaker);
      return speaker ? `SPEAKER: ${speaker}\n${text}` : text;
    })
    .filter(Boolean)
    .join('\n\n');
}

export function normalizeDiarizedTranscript(text) {
  const turns = mergeConsecutiveTurns(dedupeRepeatedConversation(parseTranscriptTurns(text)));
  if (!turns.length) return String(text || '').trim();
  return serializeTranscriptTurns(turns);
}
