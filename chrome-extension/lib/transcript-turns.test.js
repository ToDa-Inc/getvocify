import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  firstName,
  normalizeDiarizedTranscript,
  parseTranscriptTurns,
  speakerDisplayLabel,
} from './transcript-turns.js';

const DISPLAY = `Speaker 1
Hola, ángel. Soy Toni, fundador de Vox HIFI.

Speaker 2
Toni. Qué más me has dicho?

Speaker 1
He visto que estás como director de ventas en Drive Solutions.`;

const RAW = `SPEAKER: S1
Hola, ángel. Soy Toni, fundador de Vox HIFI.

SPEAKER: S2
Toni. Qué más me has dicho?

SPEAKER: S1
He visto que estás como director de ventas en Drive Solutions.`;

describe('transcript-turns', () => {
  it('parses both Speaker 1 and SPEAKER: S1', () => {
    assert.equal(parseTranscriptTurns(DISPLAY).length, 3);
    assert.equal(parseTranscriptTurns(RAW).length, 3);
  });

  it('drops a duplicated display+raw copy of the same call', () => {
    const doubled = `${DISPLAY}\n\n${RAW}`;
    const normalized = normalizeDiarizedTranscript(doubled);
    const turns = parseTranscriptTurns(normalized);
    assert.equal(turns.length, 3);
    assert.equal(turns[0].speaker, 'S1');
    assert.match(normalized, /SPEAKER: S1/);
    assert.equal((normalized.match(/Hola, ángel/g) || []).length, 1);
  });

  it('labels S1 as You and S2 as the contact first name', () => {
    assert.equal(speakerDisplayLabel('S1', { s1: 'You', s2: 'Ángel' }), 'You');
    assert.equal(speakerDisplayLabel('Speaker 2', { s1: 'You', s2: 'Ángel' }), 'Ángel');
    assert.equal(firstName('Ángel Ruiz'), 'Ángel');
  });

  it('maps named STT speakers to the contact label, not the raw name', () => {
    const named = `SPEAKER: JUAN
Sí. Buenas. ¿Qué tal?`;
    const turns = parseTranscriptTurns(named);
    assert.equal(turns[0].speaker, 'JUAN');
    assert.equal(speakerDisplayLabel('JUAN', { s1: 'You', s2: 'Francisco' }), 'Francisco');
  });
});
