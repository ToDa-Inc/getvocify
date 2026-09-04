import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  CALL_STATES,
  callButtonLabel,
  callerIdFormVisible,
  canMute,
  canSendDigits,
  contactInitials,
  dialTargetFromContact,
  floatingDialerChrome,
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

describe('floatingDialerChrome', () => {
  it('opens the sheet only while the panel is expanded', () => {
    assert.deepEqual(floatingDialerChrome(true, CALL_STATES.IDLE), {
      sheet: true,
      fab: false,
    });
    assert.deepEqual(floatingDialerChrome(false, CALL_STATES.IDLE), {
      sheet: false,
      fab: false,
    });
  });

  it('keeps a FAB when the panel is collapsed during a live call', () => {
    assert.deepEqual(floatingDialerChrome(false, CALL_STATES.RINGING), {
      sheet: false,
      fab: true,
    });
    assert.deepEqual(floatingDialerChrome(false, CALL_STATES.ACTIVE), {
      sheet: false,
      fab: true,
    });
    assert.deepEqual(floatingDialerChrome(true, CALL_STATES.ACTIVE), {
      sheet: true,
      fab: false,
    });
  });
});

describe('dialTargetFromContact', () => {
  it('normalizes the contact phone so the dashboard can dial it', () => {
    assert.equal(
      dialTargetFromContact({ phone: '+34600111222' }),
      '+34600111222',
    );
    assert.equal(dialTargetFromContact({ phone: '600111222' }), '+34600111222');
  });

  it('returns null when the contact has no dialable phone', () => {
    assert.equal(dialTargetFromContact(null), null);
    assert.equal(dialTargetFromContact({ phone: null }), null);
    assert.equal(dialTargetFromContact({ phone: 'n/a' }), null);
  });
});

describe('callerIdFormVisible', () => {
  it('shows the add-number form after load even when calling is disabled', () => {
    assert.equal(callerIdFormVisible({ isLoading: false, enabled: false }), true);
    assert.equal(callerIdFormVisible({ isLoading: false, enabled: true }), true);
    assert.equal(callerIdFormVisible({ isLoading: true, enabled: true }), false);
  });
});

describe('contactInitials', () => {
  it('uses first and last name letters', () => {
    assert.equal(contactInitials('Enrique Rodríguez'), 'ER');
  });

  it('falls back to two letters of a single name', () => {
    assert.equal(contactInitials('Juan'), 'JU');
    assert.equal(contactInitials(''), '');
  });
});
