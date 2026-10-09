import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { homeHoyCardsForDisplay } from './home-hoy.js';

describe('desktop home hoy', () => {
  const a = { id: '1', reason: 'Uno' };
  const b = { id: '2', reason: 'Dos' };

  it('hides cards while listening', () => {
    assert.deepEqual(
      homeHoyCardsForDisplay({ captureActive: true, cards: [a, b] }),
      [],
    );
  });

  it('shows two cards while idle', () => {
    assert.deepEqual(
      homeHoyCardsForDisplay({ captureActive: false, cards: [a, b] }),
      [a, b],
    );
  });

  it('shows none when idle with zero cards', () => {
    assert.deepEqual(
      homeHoyCardsForDisplay({ captureActive: false, cards: [] }),
      [],
    );
  });
});
