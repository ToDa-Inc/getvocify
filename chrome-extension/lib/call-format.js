/**
 * Pure formatting and prefill decisions for the dialer UI.
 * No chrome.* and no Twilio — keep it unit-testable.
 */

import { CALL_STATES } from './dialer.js';

export function formatCallDuration(ms) {
  const n = Number(ms);
  if (!Number.isFinite(n) || n < 0) return '0:00';
  const total = Math.floor(n / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const mm = hours > 0 ? String(minutes).padStart(2, '0') : String(minutes);
  const ss = String(seconds).padStart(2, '0');
  if (hours > 0) return `${hours}:${mm}:${ss}`;
  return `${mm}:${ss}`;
}

export function describeCallState({ state, to, answeredAt, now, muted } = {}) {
  switch (state) {
    case CALL_STATES.CONNECTING:
      return 'Conectando…';
    case CALL_STATES.RINGING:
      return to ? `Llamando a ${to}…` : 'Llamando…';
    case CALL_STATES.ACTIVE: {
      const elapsed = formatCallDuration(
        Number(now) - Number(answeredAt || now)
      );
      return muted ? `En llamada · ${elapsed} · silenciado` : `En llamada · ${elapsed}`;
    }
    case CALL_STATES.ENDING:
      return 'Colgando…';
    default:
      return '';
  }
}

export function shouldPrefillNumber({
  currentValue,
  prefilledFrom,
  contactId,
  contactPhone,
} = {}) {
  if (!contactPhone) return null;
  const typed = String(currentValue || '').trim();
  const contactChanged = Boolean(contactId) && Boolean(prefilledFrom) && contactId !== prefilledFrom;
  if (contactChanged) return contactPhone;
  if (prefilledFrom && contactId && prefilledFrom === contactId) return null;
  if (typed) return null;
  return contactPhone;
}
