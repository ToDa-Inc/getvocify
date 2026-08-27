/**
 * Dialer logic: number normalization and mutual exclusion.
 *
 * Pure module — no chrome.* and no Twilio. The offscreen document owns the
 * Twilio Device; this file owns the decisions, so they stay unit-testable.
 *
 * The mic is a single resource shared with voice memos and Listen, so a call
 * can only start when neither of those holds it.
 */

export const CALL_STATES = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  RINGING: 'ringing',
  ACTIVE: 'active',
  ENDING: 'ending',
};

const SEPARATORS = /[\s().\-/]/g;
const DIGITS_ONLY = /^\d+$/;
const E164 = /^\+[1-9]\d{7,14}$/;

/**
 * Best-effort E.164 for phone numbers coming out of CRM free-text fields.
 * Returns null rather than guessing when the value cannot be a phone number.
 */
export function normalizeDialTarget(raw, defaultCountryCode = '34') {
  if (typeof raw !== 'string') return null;
  let value = raw.replace(SEPARATORS, '').trim();
  if (!value) return null;

  if (value.startsWith('00')) {
    value = `+${value.slice(2)}`;
  } else if (!value.startsWith('+')) {
    if (!DIGITS_ONLY.test(value)) return null;

    if (value.startsWith(defaultCountryCode)) {
      const remaining = value.slice(defaultCountryCode.length);
      if (remaining.length >= 8) {
        return null;
      }
    }

    value = `+${defaultCountryCode}${value.replace(/^0+/, '')}`;
  }

  return E164.test(value) ? value : null;
}

export function canStartCall({ isRecording, isTabCapturing, callState } = {}) {
  if (isRecording) {
    return { ok: false, reason: 'Para la nota de voz antes de llamar.' };
  }
  if (isTabCapturing) {
    return { ok: false, reason: 'Para Listen antes de llamar.' };
  }
  if (callState && callState !== CALL_STATES.IDLE) {
    return { ok: false, reason: 'Ya hay una llamada en curso.' };
  }
  return { ok: true, reason: null };
}

export function callButtonLabel(callState) {
  switch (callState) {
    case CALL_STATES.CONNECTING:
      return 'Conectando…';
    case CALL_STATES.RINGING:
      return 'Llamando…';
    case CALL_STATES.ACTIVE:
      return 'Colgar';
    case CALL_STATES.ENDING:
      return 'Colgando…';
    default:
      return 'Llamar';
  }
}
