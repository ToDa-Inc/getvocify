import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { strings } from '../renderer/shared/ui/i18n.js';
import {
  latestTaggedTurnBody,
  speakerRoleFromLastLine,
  splitTaggedTranscript,
  turnRoleFromPart,
} from './transcript-turns.js';

describe('transcript-turns', () => {
  it('splits and maps rep from Spanish and English speaker prefixes', () => {
    const es = splitTaggedTranscript('Tú: hola Ellos: adiós Tú: otra vez');
    assert.equal(es.length, 3);
    assert.equal(turnRoleFromPart(es[0]), 'rep');
    assert.equal(turnRoleFromPart(es[1]), 'prospect');
    assert.equal(turnRoleFromPart(es[2]), 'rep');

    const en = splitTaggedTranscript('You: hello Them: bye You: again');
    assert.equal(en.length, 3);
    assert.equal(turnRoleFromPart(en[0]), 'rep');
    assert.equal(turnRoleFromPart(en[2]), 'rep');
    assert.equal(latestTaggedTurnBody('You: first Them: second You: latest'), 'latest');
  });

  it('leaves untagged lines without a speaker role', () => {
    const parts = splitTaggedTranscript('plain text without prefix');
    assert.equal(parts.length, 1);
    assert.equal(turnRoleFromPart(parts[0]), null);
  });

  it('speakerRoleFromLastLine uses every catalog speaker prefix', () => {
    const es = strings({ vocify_lang: 'es' });
    const en = strings({ vocify_lang: 'en' });
    assert.equal(speakerRoleFromLastLine(`${es.speakerYou}: hola`), 'rep');
    assert.equal(speakerRoleFromLastLine(`${es.speakerThem}: adiós`), 'prospect');
    assert.equal(speakerRoleFromLastLine(`${en.speakerYou}: hi`), 'rep');
    assert.equal(speakerRoleFromLastLine(`${en.speakerThem}: bye`), 'prospect');
    assert.equal(speakerRoleFromLastLine('no prefix here'), null);
  });
});
