import test from 'node:test';
import assert from 'node:assert/strict';
import { reconcileTranscript } from './transcript.js';

test('interim fragment is replaced by the final turn with the same id', () => {
  const before = { revision: 1, turns: [], interim: { id: 't1', text: 'Quedamos el mar' } };
  const incoming = { revision: 2, turns: [{ id: 't1', text: 'Quedamos el martes' }], interim: null };
  assert.deepEqual(reconcileTranscript(before, incoming), incoming);
});

test('an older revision does not replace a newer one', () => {
  const before = { revision: 1, turns: [], interim: { id: 't1', text: 'Quedamos el mar' } };
  const incoming = { revision: 2, turns: [{ id: 't1', text: 'Quedamos el martes' }], interim: null };
  assert.deepEqual(reconcileTranscript(incoming, before), incoming);
});
