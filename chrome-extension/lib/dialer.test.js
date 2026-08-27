import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  CALL_STATES,
  callButtonLabel,
  canStartCall,
  normalizeDialTarget,
} from './dialer.js';

describe('normalizeDialTarget', () => {
  it('passes through E.164', () => {
    assert.equal(normalizeDialTarget('+34600111222'), '+34600111222');
  });

  it('strips the formatting HubSpot contacts arrive with', () => {
    assert.equal(normalizeDialTarget('+34 600 111 222'), '+34600111222');
    assert.equal(normalizeDialTarget('(+34) 600-111.222'), '+34600111222');
  });

  it('adds the default country code to a national number', () => {
    assert.equal(normalizeDialTarget('600111222'), '+34600111222');
  });

  it('drops the national trunk prefix', () => {
    assert.equal(normalizeDialTarget('0600111222'), '+34600111222');
  });

  it('converts a 00 international prefix', () => {
    assert.equal(normalizeDialTarget('0034600111222'), '+34600111222');
  });

  it('honours a non-Spanish default country code', () => {
    assert.equal(normalizeDialTarget('600111222', '351'), '+351600111222');
  });

  it('returns null for junk instead of dialling it', () => {
    assert.equal(normalizeDialTarget(''), null);
    assert.equal(normalizeDialTarget('n/a'), null);
    assert.equal(normalizeDialTarget('600'), null);
    assert.equal(normalizeDialTarget(null), null);
  });

  it('rejects ambiguous numbers that already include the country code without +', () => {
    assert.equal(normalizeDialTarget('34600111222', '34'), null);
    assert.equal(normalizeDialTarget('351600111222', '351'), null);
  });

  it('accepts short national numbers that happen to start with the country code', () => {
    assert.equal(normalizeDialTarget('341234567', '34'), '+34341234567');
    assert.equal(normalizeDialTarget('351234567', '351'), '+351351234567');
  });
});

describe('canStartCall', () => {
  const idle = { isRecording: false, isTabCapturing: false, callState: CALL_STATES.IDLE };

  it('allows a call when nothing else owns the mic', () => {
    assert.deepEqual(canStartCall(idle), { ok: true, reason: null });
  });

  it('blocks while a voice memo is recording', () => {
    const result = canStartCall({ ...idle, isRecording: true });
    assert.equal(result.ok, false);
    assert.match(result.reason, /nota de voz/i);
  });

  it('blocks while Listen is capturing tab audio', () => {
    const result = canStartCall({ ...idle, isTabCapturing: true });
    assert.equal(result.ok, false);
    assert.match(result.reason, /listen/i);
  });

  it('blocks a second call while one is active', () => {
    const result = canStartCall({ ...idle, callState: CALL_STATES.ACTIVE });
    assert.equal(result.ok, false);
    assert.match(result.reason, /llamada/i);
  });

  it('blocks while a call is still connecting', () => {
    assert.equal(canStartCall({ ...idle, callState: CALL_STATES.CONNECTING }).ok, false);
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

  it('falls back to Llamar for an unknown state', () => {
    assert.equal(callButtonLabel('bogus'), 'Llamar');
  });
});
