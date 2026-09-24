import { strings } from '../renderer/shared/ui/i18n.js';
import { splitTaggedTranscript, stripSpeakerPrefix, turnRoleFromPart } from './transcript-turns.js';

/** HubSpot contact id for copilot suggest when the page is a contact record; never invent ids. */
export function contactIdForListenSession(crmPageContext) {
  if (!crmPageContext || crmPageContext.objectType !== 'contact') return null;
  const recordId = crmPageContext.recordId;
  if (recordId == null || recordId === '') return null;
  const id = String(recordId).trim();
  return id || null;
}

export function buildListenSession({ callMode = 'meeting', crmPageContext = null } = {}) {
  return {
    callMode,
    contactId: contactIdForListenSession(crmPageContext),
  };
}

export function canStartListen({
  hasToken = false,
  isListening = false,
  permissionGate = null,
} = {}) {
  if (isListening) return { ok: false, reason: 'already_listening' };
  if (!hasToken) return { ok: false, reason: 'login_required' };
  if (permissionGate && permissionGate.ok === false) {
    return { ok: false, reason: permissionGate.reason };
  }
  return { ok: true };
}

export function startDeniedMessage(reason, { platform, lang } = {}) {
  const t = strings(lang);
  switch (reason) {
    case 'already_listening':
      return t.listenDenyAlreadyListening;
    case 'login_required':
      return t.listenDenyLoginRequired;
    case 'no_system_audio':
      return platform === 'linux'
        ? t.listenDenyNoSystemAudioLinux
        : t.listenDenyNoSystemAudioMac;
    case 'no_mic':
      return t.listenDenyNoMic;
    default:
      return t.listenDenyDesktopDefault;
  }
}

export function applyTranscriptUpdate(state, { text, isFinal, audioChannel, lang } = {}) {
  const t = strings(lang);
  const finalTranscript = state.finalTranscript || '';
  const piece = typeof text === 'string' ? text : '';
  const role = audioChannel === 'rep' ? 'rep' : audioChannel === 'prospect' ? 'prospect' : null;
  const tagged = !piece
    ? ''
    : role === 'rep'
      ? `${t.speakerYou}: ${piece}`
      : role === 'prospect'
        ? `${t.speakerThem}: ${piece}`
        : piece;

  if (isFinal) {
    if (!piece) return { finalTranscript, interimTranscript: '' };
    if (role && finalTranscript) {
      const parts = splitTaggedTranscript(finalTranscript);
      const last = parts[parts.length - 1] || '';
      if (turnRoleFromPart(last) === role) {
        const body = `${stripSpeakerPrefix(last)} ${piece}`.replace(/\s+/g, ' ').trim();
        const label = role === 'rep' ? t.speakerYou : t.speakerThem;
        parts[parts.length - 1] = `${label}: ${body}`;
        return { finalTranscript: parts.join(' '), interimTranscript: '' };
      }
    }
    return {
      finalTranscript: tagged ? (finalTranscript ? `${finalTranscript} ${tagged}` : tagged) : finalTranscript,
      interimTranscript: '',
    };
  }
  return {
    finalTranscript,
    interimTranscript: tagged || piece,
  };
}
