/**
 * Pure formatting and visibility decisions for the dialer UI.
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

function formatPhoneCaption(e164) {
  const value = String(e164 || '');
  const digits = value.replace(/\D/g, '');
  if (value.startsWith('+34') && digits.length === 11) {
    const national = digits.slice(2);
    return `+34 ${national.slice(0, 3)} ${national.slice(3, 5)} ${national.slice(5, 7)} ${national.slice(7)}`;
  }
  return value;
}

export function contactCallCta({
  contactPhone,
  contactName,
  callState,
  canPlaceCall = true,
} = {}) {
  const phone = String(contactPhone || '').trim();
  const inCall = Boolean(callState && callState !== CALL_STATES.IDLE);
  if (!phone || inCall || canPlaceCall === false) {
    return { visible: false, phone: null, label: '', caption: '' };
  }
  const first = String(contactName || '').trim().split(/\s+/)[0];
  return {
    visible: true,
    phone,
    label: first ? `Llamar a ${first}` : 'Llamar a este contacto',
    caption: formatPhoneCaption(phone),
  };
}

export function dialerPanelMode({
  contactPhone,
  callState,
  lastCall,
  canPlaceCall = true,
} = {}) {
  const inCall = Boolean(callState && callState !== CALL_STATES.IDLE);
  if (inCall) return 'live';
  if (lastCall && lastCall.outcome === 'answered') return 'postcall';
  const phone = String(contactPhone || '').trim();
  if (phone && canPlaceCall === false) return 'needs-cli';
  if (phone) return 'contact';
  return 'hidden';
}

export function postCallNotice(lastCall) {
  if (!lastCall || lastCall.outcome === 'answered') {
    return { visible: false, text: '' };
  }
  const error = String(lastCall.errorMessage || '');
  if (/31005/i.test(error) || /application error/i.test(error)) {
    return { visible: true, text: 'Twilio no alcanzó el servidor' };
  }
  if (error) return { visible: true, text: error };
  return { visible: true, text: 'Sin respuesta' };
}
