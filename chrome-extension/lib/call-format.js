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
    case CALL_STATES.ACTIVE:
      return 'En llamada';
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
  if (!phone || inCall) {
    return { visible: false, phone: null, label: '', caption: '', ready: false };
  }
  const first = String(contactName || '').trim().split(/\s+/)[0];
  const ready = canPlaceCall !== false;
  return {
    visible: true,
    phone,
    label: first ? `Llamar a ${first}` : 'Llamar a este contacto',
    caption: formatPhoneCaption(phone),
    ready,
  };
}

export function shouldShowContactCallCta(mode, cta) {
  return Boolean(
    cta?.visible && (mode === 'contact' || mode === 'needs-cli' || mode === 'setup')
  );
}

export function contactCallHint({ mode, objectType, hasPhone } = {}) {
  if (mode === 'needs-cli') {
    return {
      text: 'Add your number in Calling settings to place this call',
      action: 'calling-settings',
    };
  }
  if (mode === 'setup') {
    return {
      text: "Calling isn't set up for this account. Open Calling settings.",
      action: 'calling-settings',
    };
  }
  if (objectType === 'contact' && !hasPhone) {
    return { text: 'No phone number on this contact', action: null };
  }
  return { text: '', action: null };
}

export function contactCallTooltip({ ready, caption, hint } = {}) {
  if (!ready && hint?.text) return hint.text;
  return String(caption || '');
}

export function dialerPanelMode({
  contactPhone,
  callState,
  lastCall,
  canPlaceCall = true,
  callingEnabled = true,
} = {}) {
  const inCall = Boolean(callState && callState !== CALL_STATES.IDLE);
  if (inCall) return 'live';
  if (lastCall && lastCall.outcome === 'answered') return 'postcall';
  const phone = String(contactPhone || '').trim();
  if (!callingEnabled) return phone ? 'setup' : 'hidden';
  if (phone && canPlaceCall === false) return 'needs-cli';
  if (phone) return 'contact';
  return 'hidden';
}

/** Same copy as `src/lib/dial-session.ts` `dispositionMessage`. */
export function dispositionMessage(disposition) {
  const value = String(disposition || '').toLowerCase();
  if (value === 'busy') return 'Ocupado';
  if (value === 'no_answer' || value === 'no-answer' || value === 'no_response') {
    return 'Sin respuesta';
  }
  if (value === 'canceled' || value === 'cancelled') return 'Llamada cancelada';
  if (value === 'failed') return 'Llamada fallida';
  return null;
}

/** Twilio Voice SDK 31005 after Dial hangs up the parent leg — not a Voice URL miss. */
export function isCarrierHangupError(error) {
  if (error && typeof error === 'object' && Number(error.code) === 31005) return true;
  const text = String(error || '');
  return /\b31005\b/.test(text) || /error sent from gateway in hangup/i.test(text);
}

/**
 * Voice JS SDK maps a gateway HANGUP `{code:31000,message:General Error}` to
 * UnknownError. Same string for Dial timeout and for PSTN `failed` (e.g. 13227).
 * Hide the raw SDK copy; map from DialCallStatus instead.
 */
export function isVoiceSdkGeneralError(error) {
  if (error && typeof error === 'object' && Number(error.code) === 31000) return true;
  return /\b31000\b/.test(String(error || ''));
}

const VOICE_TOKEN_CODES = new Set([20101, 20104, 20105, 31204, 31205]);

function errorText(error) {
  if (!error) return '';
  if (typeof error === 'string') return error;
  return String(error.message || error.data?.detail || error);
}

/** Twilio Voice JWT dead or not yet valid — minting a new one + new Device fixes it. */
export function isVoiceAccessTokenError(error) {
  const code = error && typeof error === 'object' ? Number(error.code) : NaN;
  if (VOICE_TOKEN_CODES.has(code)) return true;
  const text = errorText(error);
  return (
    /\b(20101|20104|20105|31204|31205)\b/.test(text)
    || /access.?token/i.test(text)
    || /jwt token (expired|invalid)/i.test(text)
  );
}

/** Chrome killed the extension service worker or the offscreen page. Reload / second click recovers. */
export function isExtensionRuntimeError(error) {
  const text = errorText(error);
  return (
    /receiving end does not exist/i.test(text)
    || /message port closed/i.test(text)
    || /extension context invalidated/i.test(text)
    || /service worker/i.test(text)
    || /worker service/i.test(text)
  );
}

export function isVocifySessionError(error) {
  if (error && typeof error === 'object' && Number(error.status) === 401) return true;
  return /session expired|invalid or expired session|please sign in/i.test(errorText(error));
}

export const CALL_ERROR_TOKEN_STALE = 'La sesión de llamada caducó. Pulsa Llamar otra vez.';
export const CALL_ERROR_EXTENSION_RESTARTED = 'Vocify se reinició. Pulsa Llamar otra vez.';
export const CALL_ERROR_SESSION = 'Tu sesión de Vocify caducó. Recarga la extensión.';
export const CALL_ERROR_START = 'No se pudo iniciar la llamada.';
export const CALL_ERROR_TOKEN_FETCH = 'No se pudo obtener el token de llamada.';

/** Hide Twilio/Chrome jargon. 31005/31000 stay null — DialCallStatus owns that copy. */
export function userFacingCallError(error, fallback = CALL_ERROR_START) {
  if (isCarrierHangupError(error) || isVoiceSdkGeneralError(error)) return null;
  if (isVocifySessionError(error)) return CALL_ERROR_SESSION;
  if (isExtensionRuntimeError(error)) return CALL_ERROR_EXTENSION_RESTARTED;
  if (isVoiceAccessTokenError(error)) return CALL_ERROR_TOKEN_STALE;
  const text = errorText(error).trim();
  if (!text) return fallback;
  if (/twilio/i.test(text)) return fallback;
  return text;
}

export function userFacingCallSetupError(error) {
  if (isVocifySessionError(error)) return CALL_ERROR_SESSION;
  if (isExtensionRuntimeError(error)) return CALL_ERROR_EXTENSION_RESTARTED;
  return CALL_ERROR_TOKEN_FETCH;
}

/** Same busy copy as HubSpot rows (`src/lib/recordings.ts`) and memo rows. */
function isScreenedOut(outcome) {
  const value = String(outcome || '').trim();
  return value === 'voicemail' || value === 'no_response';
}

export function memoBusyLabel(status) {
  if (status === 'uploading') return 'Uploading';
  if (status === 'extracting') return 'Extracting';
  if (status === 'transcribing') return 'Transcribing';
  return null;
}

const MEMO_IN_FLIGHT = new Set([
  'uploading',
  'transcribing',
  'extracting',
  'pending_transcript',
]);

/**
 * HubSpot can mark outbound_calls.logged while the memo is still extracting.
 * Stop only when the memo is no longer in flight (and, if auto-sync is on,
 * after pending_review has been approved or screening skipped the write).
 */
export function isCallPollTerminal(call = {}, { autoSync = false } = {}) {
  const disposition = call.callDisposition || call.disposition || null;
  const memoStatus = call.memoStatus || null;
  if (MEMO_IN_FLIGHT.has(memoStatus)) return false;
  if (call.status === 'recorded') return false;
  if (call.memoId && !memoStatus) return false;
  if (
    autoSync
    && memoStatus === 'pending_review'
    && !isScreenedOut(call.screeningOutcome)
  ) {
    return false;
  }
  if (call.status === 'failed') return true;
  if (['approved', 'rejected', 'failed'].includes(memoStatus)) return true;
  if (['busy', 'no_answer', 'canceled', 'failed'].includes(disposition)) return true;
  return call.status === 'logged';
}

/**
 * Activity chrome for a Vocify outbound call. Uses memo status, not call.status.
 * dialing is not transcription.
 */
export function outboundActivityChrome(call = {}) {
  const memoId = call.memoId || null;
  const memoStatus = call.memoStatus || null;
  const autoSync = Boolean(call.autoSync);
  const busy = memoBusyLabel(memoStatus);
  if (busy) return { kind: 'busy', label: busy };
  if (memoId && memoStatus === 'pending_review' && autoSync && !isScreenedOut(call.screeningOutcome)) {
    return { kind: 'busy', label: 'Writing' };
  }
  if (memoId && (memoStatus === 'pending_review' || memoStatus === 'pending_transcript')) {
    return { kind: 'continue', label: 'Continue', memoId };
  }
  if (memoId && memoStatus === 'approved') {
    return { kind: 'view', label: 'View', memoId };
  }
  if (call.status === 'recorded' && !memoStatus) {
    return { kind: 'busy', label: 'Processing' };
  }
  const disposition = call.callDisposition || call.disposition
    || (['busy', 'no_answer', 'canceled', 'failed'].includes(call.status) ? call.status : null);
  const missed = dispositionMessage(disposition);
  if (missed && disposition !== 'failed') {
    return { kind: 'status', label: missed };
  }
  if ((call.status === 'failed' || disposition === 'failed') && call.to) {
    return { kind: 'redial', label: 'Reintentar', to: call.to, from: call.from || '' };
  }
  return { kind: 'none', label: '' };
}

export function postCallCard({
  memoStatus,
  memoId,
  durationLabel = '',
  autoSync = false,
  errorMessage = '',
  processing,
  screeningOutcome,
} = {}) {
  const duration = durationLabel || '0:00';
  if (
    errorMessage
    && !isCarrierHangupError(errorMessage)
    && processing === false
    && memoStatus !== 'pending_review'
    && memoStatus !== 'approved'
  ) {
    return { kind: 'error', text: errorMessage };
  }
  if (memoStatus === 'approved' && memoId) {
    return {
      kind: 'synced',
      text: `Llamada de ${duration} · escrito en CRM`,
      actionLabel: 'Ver',
      memoId,
    };
  }
  if (memoStatus === 'pending_review' && memoId) {
    if (isScreenedOut(screeningOutcome)) {
      return {
        kind: 'review',
        text: screeningOutcome === 'voicemail'
          ? `Llamada de ${duration} · marcada como buzón`
          : `Llamada de ${duration} · sin conversación`,
        actionLabel: 'Revisar',
        memoId,
      };
    }
    if (autoSync) {
      return { kind: 'busy', text: `Llamada de ${duration} · escribiendo en CRM` };
    }
    return {
      kind: 'review',
      text: `Llamada de ${duration} · listo para revisar`,
      actionLabel: 'Revisar',
      memoId,
    };
  }
  const busy = memoBusyLabel(memoStatus) || 'Processing';
  return { kind: 'busy', text: `Llamada de ${duration} · ${busy}` };
}

export function snapshotCallOutcome({ callState, answeredAt } = {}) {
  if (answeredAt || callState === CALL_STATES.ACTIVE) return 'answered';
  return 'no_answer';
}

export function lastCallAsOutbound(lastCall) {
  if (!lastCall?.callSid) return null;
  let status = 'logged';
  if (lastCall.processing) status = 'recorded';
  else if (lastCall.disposition === 'busy') status = 'busy';
  else if (lastCall.disposition === 'canceled' || lastCall.disposition === 'cancelled') status = 'canceled';
  else if (lastCall.disposition === 'failed') status = 'failed';
  else if (/application error/i.test(String(lastCall.errorMessage || ''))) status = 'failed';
  else if (lastCall.outcome === 'no_answer') status = lastCall.disposition || 'no_answer';
  else if (!lastCall.memoStatus) status = 'recorded';
  return {
    callSid: lastCall.callSid,
    startedAt: lastCall.answeredAt || lastCall.endedAt || null,
    answeredAt: lastCall.answeredAt || null,
    memoId: lastCall.memoId || null,
    memoStatus: lastCall.memoStatus || null,
    screeningOutcome: lastCall.screeningOutcome || null,
    disposition: lastCall.disposition || null,
    to: lastCall.to || null,
    from: lastCall.callerId || null,
    status,
  };
}

export function applyCallPoll(lastCall, call, { autoSync = false } = {}) {
  if (!lastCall) return lastCall;
  const disposition = call.callDisposition || lastCall.disposition || null;
  const hangupNoise = isCarrierHangupError(lastCall.errorMessage);
  const apiError = call.errorMessage || null;
  const errorMessage = apiError || (hangupNoise ? null : lastCall.errorMessage || null);
  const terminal = isCallPollTerminal({ ...call, disposition }, { autoSync });
  return {
    ...lastCall,
    memoId: call.memoId || lastCall.memoId || null,
    memoStatus: call.memoStatus || lastCall.memoStatus || null,
    screeningOutcome: call.screeningOutcome || lastCall.screeningOutcome || null,
    durationSeconds: call.durationSeconds ?? lastCall.durationSeconds,
    disposition,
    errorMessage: dispositionMessage(disposition) ? null : errorMessage,
    processing: lastCall.outcome === 'answered' ? !terminal : false,
  };
}

export function postCallNotice(lastCall) {
  if (!lastCall || lastCall.outcome === 'answered') {
    return { visible: false, text: '' };
  }
  const fromDisposition = dispositionMessage(lastCall.disposition);
  if (fromDisposition) return { visible: true, text: fromDisposition };
  const error = String(lastCall.errorMessage || '');
  if (isCarrierHangupError(error)) {
    return { visible: true, text: 'Sin respuesta' };
  }
  if (isVoiceSdkGeneralError(error)) {
    return { visible: false, text: '' };
  }
  if (/application error/i.test(error)) {
    return { visible: true, text: 'Twilio no alcanzó el servidor' };
  }
  if (error) return { visible: true, text: error };
  return { visible: true, text: 'Sin respuesta' };
}
