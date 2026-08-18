import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { TurnDetector } from './turn-detector.js';

describe('TurnDetector', () => {
  it('does not fire before settleMs even when interim is empty', () => {
    const turns = [];
    const detector = new TurnDetector({
      settleMs: 50,
      minWords: 6,
      now: () => 0,
      onTurn: (turn) => turns.push(turn),
    });
    detector.setEnabled(true);
    detector.onFinalTranscript('this is a real objection from the prospect');
    detector.onInterim('');
    detector.tick(10);
    assert.equal(turns.length, 0);
  });

  it('fires the pending final after settleMs of empty interim', () => {
    const turns = [];
    const detector = new TurnDetector({
      settleMs: 50,
      minWords: 6,
      now: () => 0,
      onTurn: (turn, full) => turns.push({ turn, full }),
    });
    detector.setEnabled(true);
    detector.onFinalTranscript('this is a real objection from the prospect');
    detector.onInterim('');
    detector.tick(50);
    assert.equal(turns.length, 1);
    assert.equal(turns[0].turn, 'this is a real objection from the prospect');
    assert.equal(turns[0].full, 'this is a real objection from the prospect');
  });

  it('skips turns shorter than minWords', () => {
    const turns = [];
    const detector = new TurnDetector({
      settleMs: 10,
      minWords: 6,
      now: () => 0,
      onTurn: (turn) => turns.push(turn),
    });
    detector.setEnabled(true);
    detector.onFinalTranscript('too short');
    detector.onInterim('');
    detector.tick(10);
    assert.equal(turns.length, 0);
  });

  it('flushes immediately on EndOfUtterance', () => {
    const turns = [];
    const detector = new TurnDetector({
      settleMs: 5000,
      minWords: 6,
      now: () => 0,
      onTurn: (turn) => turns.push(turn),
    });
    detector.setEnabled(true);
    detector.onFinalTranscript('this is a real objection from the prospect');
    detector.onEndOfUtterance();
    assert.equal(turns.length, 1);
  });

  it('labels flushed turns as prospect when constructed for source labeling', () => {
    const metas = [];
    const detector = new TurnDetector({
      settleMs: 10,
      minWords: 6,
      speakerRole: 'prospect',
      now: () => 0,
      onTurn: (_turn, _full, meta) => metas.push(meta),
    });
    detector.setEnabled(true);
    detector.onFinalTranscript('this is a real objection from the prospect');
    detector.onEndOfUtterance();
    assert.equal(metas[0].speakerRole, 'prospect');
  });
});
