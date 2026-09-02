import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { CALL_STATES } from './dialer.js';
import {
  describeCallState,
  formatCallDuration,
  shouldPrefillNumber,
} from './call-format.js';

describe('formatCallDuration', () => {
  it('formats seconds as m:ss', () => {
    assert.equal(formatCallDuration(0), '0:00');
    assert.equal(formatCallDuration(7000), '0:07');
    assert.equal(formatCallDuration(59000), '0:59');
    assert.equal(formatCallDuration(60000), '1:00');
    assert.equal(formatCallDuration(723000), '12:03');
  });

  it('formats hours', () => {
    assert.equal(formatCallDuration(3661000), '1:01:01');
  });

  it('treats negative and non-finite as 0:00', () => {
    assert.equal(formatCallDuration(-1), '0:00');
    assert.equal(formatCallDuration(NaN), '0:00');
    assert.equal(formatCallDuration(Infinity), '0:00');
    assert.equal(formatCallDuration(undefined), '0:00');
  });
});

describe('describeCallState', () => {
  it('labels connecting, ringing, ending', () => {
    assert.equal(describeCallState({ state: CALL_STATES.CONNECTING }), 'Conectando…');
    assert.equal(
      describeCallState({ state: CALL_STATES.RINGING, to: '+34600111222' }),
      'Llamando a +34600111222…'
    );
    assert.equal(describeCallState({ state: CALL_STATES.ENDING }), 'Colgando…');
  });

  it('includes duration and mute on active', () => {
    const now = 10_000;
    assert.equal(
      describeCallState({
        state: CALL_STATES.ACTIVE,
        answeredAt: 3000,
        now,
        muted: false,
      }),
      'En llamada · 0:07'
    );
    assert.match(
      describeCallState({
        state: CALL_STATES.ACTIVE,
        answeredAt: 3000,
        now,
        muted: true,
      }),
      /silenciado/
    );
  });
});

describe('shouldPrefillNumber', () => {
  it('fills when the box is empty and a contact phone is known', () => {
    assert.equal(
      shouldPrefillNumber({
        currentValue: '',
        prefilledFrom: null,
        contactId: 'C1',
        contactPhone: '+34600111222',
      }),
      '+34600111222'
    );
  });

  it('returns the new phone when the contact changes', () => {
    assert.equal(
      shouldPrefillNumber({
        currentValue: '+34600111222',
        prefilledFrom: 'C1',
        contactId: 'C2',
        contactPhone: '+34600999999',
      }),
      '+34600999999'
    );
  });

  it('does not clobber a user-typed number on the same contact', () => {
    assert.equal(
      shouldPrefillNumber({
        currentValue: '600111000',
        prefilledFrom: 'C1',
        contactId: 'C1',
        contactPhone: '+34600111222',
      }),
      null
    );
  });

  it('returns null when the contact is unchanged', () => {
    assert.equal(
      shouldPrefillNumber({
        currentValue: '+34600111222',
        prefilledFrom: 'C1',
        contactId: 'C1',
        contactPhone: '+34600111222',
      }),
      null
    );
  });
});
