import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  CALL_STATES,
  callButtonLabel,
  canMute,
  canSendDigits,
  formatCallerIdDisplay,
  formatLiveDuration,
  normalizeDialTarget,
} from './dial-target.ts';

describe('normalizeDialTarget', () => {
  it('passes through E.164', () => {
    assert.equal(normalizeDialTarget('+34600111222'), '+34600111222');
  });

  it('adds the default country code to a national number', () => {
    assert.equal(normalizeDialTarget('600111222'), '+34600111222');
  });

  it('returns null for junk instead of dialling it', () => {
    assert.equal(normalizeDialTarget(''), null);
    assert.equal(normalizeDialTarget('n/a'), null);
  });
});

describe('callButtonLabel', () => {
  it('labels every state', () => {
    assert.equal(callButtonLabel(CALL_STATES.IDLE), 'Llamar');
    assert.equal(callButtonLabel(CALL_STATES.CONNECTING), 'Conectando…');
    assert.equal(callButtonLabel(CALL_STATES.RINGING), 'Llamando…');
    assert.equal(callButtonLabel(CALL_STATES.ACTIVE), 'Colgar');
    assert.equal(callButtonLabel(CALL_STATES.ENDING), 'Colgando…');
  });
});

describe('canSendDigits / canMute', () => {
  it('are true only while the call is active', () => {
    assert.equal(canSendDigits(CALL_STATES.ACTIVE), true);
    assert.equal(canMute(CALL_STATES.ACTIVE), true);
    assert.equal(canSendDigits(CALL_STATES.IDLE), false);
    assert.equal(canMute(CALL_STATES.IDLE), false);
  });
});

describe('formatLiveDuration', () => {
  it('formats elapsed milliseconds as m:ss', () => {
    assert.equal(formatLiveDuration(0), '0:00');
    assert.equal(formatLiveDuration(65_000), '1:05');
  });
});

describe('formatCallerIdDisplay', () => {
  it('groups a Spanish mobile for the CLI caption', () => {
    assert.equal(formatCallerIdDisplay('+34669701069'), '+34 669 70 10 69');
  });
});
