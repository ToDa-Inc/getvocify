import test from 'node:test';
import assert from 'node:assert/strict';
import { reconcileTranscript, scrollFollow } from './transcript.js';

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

test('a confirmed turn drops the interim with the same id', () => {
  const view = reconcileTranscript(
    { revision: 1, turns: [], interim: { id: 't1', text: 'Quedamos el mar' } },
    { revision: 2, turns: [{ id: 't1', text: 'Quedamos el martes' }], interim: { id: 't1', text: 'Quedamos el mar' } },
  );
  assert.equal(view.turns.length, 1);
  assert.equal(view.turns[0].text, 'Quedamos el martes');
  assert.equal(view.interim, null);
});

test('reading above the end offers return to live and does not follow', () => {
  const intent = scrollFollow({ scrollTop: 0, scrollHeight: 800, clientHeight: 200 });
  assert.equal(intent.follow, false);
  assert.equal(intent.showReturnToLive, true);
  assert.equal(intent.label, 'Volver al directo');
  assert.equal(scrollFollow({ scrollTop: 600, scrollHeight: 800, clientHeight: 200 }).follow, true);
});
