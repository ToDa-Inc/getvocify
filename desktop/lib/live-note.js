const squash = (s) => String(s || '').replace(/\s+/g, ' ').trim();
const join = (a, b) => squash(`${a} ${b}`);

export function emptyNote() {
  return { turns: [] };
}

function openTurn(turns, speaker) {
  const last = turns[turns.length - 1];
  const changed = last && speaker && last.speaker && speaker !== last.speaker;
  if (last && !changed) {
    if (speaker && !last.speaker) turns[turns.length - 1] = { ...last, speaker };
    return turns.length - 1;
  }
  turns.push({ speaker: speaker || '', committed: '', live: '' });
  return turns.length - 1;
}

export function applyChunk(note, { text, isFinal, speaker = '' }) {
  const piece = squash(text);
  if (!piece) return note;
  const turns = note.turns.map((t) => ({ ...t }));
  const i = openTurn(turns, speaker);
  const turn = turns[i];
  if (!isFinal) {
    turn.live = piece;
    return { turns };
  }
  if (!turn.committed || piece.startsWith(turn.committed)) turn.committed = piece;
  else turn.committed = join(turn.committed, piece);
  turn.live = '';
  return { turns };
}

export function noteUploadText(note, { you, them }) {
  return note.turns
    .map((t) => {
      const body = join(t.committed, t.live);
      if (!body) return '';
      const label = t.speaker === 'rep' ? you : t.speaker === 'prospect' ? them : '';
      return label ? `${label}: ${body}` : body;
    })
    .filter(Boolean)
    .join(' ');
}

export function latestFinal(note) {
  for (let i = note.turns.length - 1; i >= 0; i -= 1) {
    if (note.turns[i].committed) return note.turns[i].committed;
  }
  return '';
}
