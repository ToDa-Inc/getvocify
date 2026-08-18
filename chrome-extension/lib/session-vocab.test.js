import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mergeSessionVocab } from './session-vocab.js';

describe('mergeSessionVocab', () => {
  it('adds caller and seller company, drops email and phone', () => {
    const vocab = mergeSessionVocab(
      ['Eneritz Garcia', 'jean@cikautxo.com', '+34 666 111 222', 'Cikautxo'],
      { full_name: 'Dany Izal', company_name: 'Vocify' },
    );
    assert.deepEqual(vocab, ['Eneritz Garcia', 'Cikautxo', 'Dany Izal', 'Vocify']);
  });

  it('dedupes case-insensitively', () => {
    const vocab = mergeSessionVocab(['Vocify'], { company_name: 'vocify' });
    assert.deepEqual(vocab, ['Vocify']);
  });
});
