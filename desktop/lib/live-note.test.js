import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { applyChunk, emptyNote, latestFinal, noteUploadText } from './live-note.js';

const feed = (note, rows) => rows.reduce((n, r) => applyChunk(n, r), note);

describe('live note', () => {
  it('joins one-word finals from the same speaker into one paragraph', () => {
    const note = feed(emptyNote(), [
      { text: 'hola', isFinal: true, speaker: 'prospect' },
      { text: 'qué', isFinal: true, speaker: 'prospect' },
      { text: 'tal', isFinal: true, speaker: 'prospect' },
    ]);
    assert.equal(note.turns.length, 1);
    assert.equal(note.turns[0].committed, 'hola qué tal');
  });

  it('keeps interim as the live tail of the same paragraph and replaces it in place', () => {
    let note = feed(emptyNote(), [{ text: 'quedamos', isFinal: true, speaker: 'rep' }]);
    note = applyChunk(note, { text: 'el mar', isFinal: false, speaker: 'rep' });
    note = applyChunk(note, { text: 'el martes', isFinal: false, speaker: 'rep' });
    assert.equal(note.turns.length, 1);
    assert.equal(note.turns[0].live, 'el martes');
    note = applyChunk(note, { text: 'el martes', isFinal: true, speaker: 'rep' });
    assert.equal(note.turns[0].committed, 'quedamos el martes');
    assert.equal(note.turns[0].live, '');
  });

  it('opens a new paragraph only when the known speaker changes', () => {
    const note = feed(emptyNote(), [
      { text: 'hola', isFinal: true, speaker: 'rep' },
      { text: 'buenas', isFinal: true, speaker: '' },
      { text: 'sí', isFinal: true, speaker: 'prospect' },
    ]);
    assert.equal(note.turns.length, 2);
    assert.equal(note.turns[0].committed, 'hola buenas');
  });

  it('does not duplicate a final that repeats the committed text', () => {
    const note = feed(emptyNote(), [
      { text: 'hola', isFinal: true, speaker: 'rep' },
      { text: 'hola qué tal', isFinal: true, speaker: 'rep' },
    ]);
    assert.equal(note.turns[0].committed, 'hola qué tal');
  });

  it('uploads committed and live text with speaker labels', () => {
    let note = feed(emptyNote(), [{ text: 'hola', isFinal: true, speaker: 'rep' }]);
    note = applyChunk(note, { text: 'vale', isFinal: false, speaker: 'prospect' });
    assert.equal(noteUploadText(note, { you: 'Tú', them: 'Cliente' }), 'Tú: hola Cliente: vale');
    assert.equal(latestFinal(note), 'hola');
  });
});
