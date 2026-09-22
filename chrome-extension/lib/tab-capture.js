import { strings } from '../shared/ui/i18n.js';

/**
 * Tab-capture policy for live call copilot.
 *
 * Constraints come from Chrome’s tabCapture + offscreen sample, not invention:
 * https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture
 * https://developer.chrome.com/docs/extensions/reference/api/tabCapture
 */

export function canStartTabCapture({
  isRecording = false,
  isCopilotListening = false,
  hasToken = false,
  tabId = null,
  hasStreamId = false,
  callState,
} = {}) {
  if (callState != null && callState !== 'idle') {
    return { ok: false, reason: 'call_in_progress' };
  }
  if (isCopilotListening) return { ok: false, reason: 'already_listening' };
  if (isRecording) return { ok: false, reason: 'mic_recording' };
  if (!hasToken) return { ok: false, reason: 'login_required' };
  if (tabId == null && !hasStreamId) return { ok: false, reason: 'no_tab' };
  return { ok: true };
}

export function startDeniedMessage(reason, lang) {
  const t = strings(lang);
  switch (reason) {
    case 'call_in_progress':
      return t.listenDenyCallInProgress;
    case 'mic_recording':
      return t.listenDenyMicRecording;
    case 'already_listening':
      return t.listenDenyAlreadyListeningTab;
    case 'login_required':
      return t.listenDenyLoginRequiredTab;
    case 'no_tab':
      return t.listenDenyNoTab;
    case 'no_stream_id':
      return t.listenDenyNoStreamId;
    case 'not_hubspot_tab':
      return t.listenDenyNotHubspotTab;
    case 'unsupported_meeting_tab':
      return t.listenDenyUnsupportedMeetingTab;
    case 'no_audio':
      return t.listenDenyNoAudio;
    case 'stream_expired':
      return t.listenDenyStreamExpired;
    case 'capture_failed':
      return t.listenDenyCaptureFailed;
    default:
      return t.listenDenyTabCaptureDefault;
  }
}

/**
 * Exact getUserMedia constraints from Chrome’s Tab Capture – Recorder sample.
 * Audio-only chromeMediaSource:"tab" is not what the official sample uses.
 */
export function tabCaptureGetUserMediaConstraints(streamId) {
  return {
    audio: {
      mandatory: {
        chromeMediaSource: 'tab',
        chromeMediaSourceId: streamId,
      },
    },
    video: {
      mandatory: {
        chromeMediaSource: 'tab',
        chromeMediaSourceId: streamId,
      },
    },
  };
}

/**
 * USER_MEDIA: redeem tab stream via getUserMedia.
 * AUDIO_PLAYBACK: loop captured audio to destination (tabCapture mutes the tab).
 * Do not include DISPLAY_MEDIA — that is the Chrome “Choose what to share” picker.
 */
export function tabCaptureOffscreenReasons() {
  return ['USER_MEDIA', 'AUDIO_PLAYBACK'];
}

/**
 * Chrome 116+ sample order:
 * https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture
 */
export function tabCaptureStartSequence() {
  return ['ensure_offscreen', 'getMediaStreamId', 'offscreen_getUserMedia'];
}

/**
 * GET_STATE in this extension awaits tabs.query. Either one consumes the Listen
 * click before chrome.tabCapture.getMediaStreamId can use it.
 */
export const LISTEN_CLICK_MUST_NOT_AWAIT = Object.freeze(['GET_STATE', 'tabs.query']);

export function isListenSessionActive(phase) {
  return phase === 'starting' || phase === 'live';
}

export function resolveListenPhase({
  listenPhase = null,
  isCopilotListening = false,
  copilotError = null,
} = {}) {
  if (listenPhase === 'starting' || listenPhase === 'live') return listenPhase;
  if (isCopilotListening) return 'live';
  if (listenPhase === 'error' || copilotError) return 'error';
  return 'idle';
}

export function listenClickRuntimeMessage({
  isCopilotListening = false,
  listenPhase = 'idle',
  captureTabId = null,
  streamId = null,
  commandSeq = null,
} = {}) {
  const phase = resolveListenPhase({ listenPhase, isCopilotListening });
  if (isListenSessionActive(phase)) {
    return commandSeq != null
      ? { type: 'STOP_TAB_CAPTURE', commandSeq }
      : { type: 'STOP_TAB_CAPTURE' };
  }
  const start = {
    type: 'START_TAB_CAPTURE',
    tabId: captureTabId ?? null,
    streamId: streamId ?? null,
  };
  if (commandSeq != null) start.commandSeq = commandSeq;
  return start;
}

export function classifyTabCaptureUrl(url) {
  if (!url || typeof url !== 'string') return { kind: 'unknown' };
  let host = '';
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return { kind: 'unknown' };
  }
  if (host === 'hubspot.com' || host.endsWith('.hubspot.com')) return { kind: 'hubspot' };
  if (host === 'pipedrive.com' || host.endsWith('.pipedrive.com')) return { kind: 'pipedrive' };
  if (
    host === 'meet.google.com' ||
    host === 'zoom.us' ||
    host.endsWith('.zoom.us') ||
    host.endsWith('.zoom.com') ||
    host.endsWith('teams.microsoft.com') ||
    host === 'teams.live.com'
  ) {
    return { kind: 'meeting_app' };
  }
  return { kind: 'other' };
}

export function listenReasonFromOffscreenError(message) {
  const text = String(message || '');
  if (/no audio/i.test(text)) return 'no_audio';
  if (/expired|invalid|ended|could not start/i.test(text)) return 'stream_expired';
  return 'capture_failed';
}

export function listenFailureReason({ canStartReason = null, streamId = null, pageUrl = null, offscreenError = null } = {}) {
  if (canStartReason) return canStartReason;
  if (offscreenError) return listenReasonFromOffscreenError(offscreenError);
  if (!streamId) {
    const kind = classifyTabCaptureUrl(pageUrl).kind;
    if (kind === 'meeting_app') return 'unsupported_meeting_tab';
    if (kind === 'other') return 'not_hubspot_tab';
    return 'no_stream_id';
  }
  return 'capture_failed';
}

export function listenUiModel({
  lang,
  listenPhase = null,
  isCopilotListening = false,
  copilotError = null,
  tabTitle = null,
  heardAnything = false,
} = {}) {
  const t = strings(lang);
  const startingStatus = t.listenStartingButton.replace(/\u2026$|\.\.\.$/, '').trim() || t.listenStartingButton;
  const phase = resolveListenPhase({ listenPhase, isCopilotListening, copilotError });
  switch (phase) {
    case 'starting':
      return {
        phase: 'starting',
        buttonLabel: t.listenStartingButton,
        statusLabel: startingStatus,
        header: t.listenStartingHeader,
        line: t.listenStartingLine,
        live: false,
      };
    case 'live':
      return {
        phase: 'live',
        buttonLabel: t.listenStopButton,
        statusLabel: heardAnything ? t.listenLiveStatus : t.listenLiveWaiting,
        header: tabTitle ? t.listenHeaderTab(tabTitle) : t.listenHeaderPlain,
        line: heardAnything
          ? (tabTitle ? t.listenLineTab(tabTitle) : t.listenLinePlain)
          : t.listenLineMic,
        live: true,
      };
    case 'error':
      return {
        phase: 'error',
        buttonLabel: t.listenIdleButton,
        statusLabel: t.listenNotListening,
        header: t.listenReady,
        line: copilotError || startDeniedMessage('capture_failed', lang),
        live: false,
      };
    default:
      return {
        phase: 'idle',
        buttonLabel: t.listenIdleButton,
        statusLabel: t.listenIdleStatus,
        header: t.listenReady,
        line: null,
        live: false,
      };
  }
}

export function isListenEpochCurrent(epoch, minEpoch) {
  const e = Number(epoch);
  const m = Number(minEpoch);
  return Number.isFinite(e) && e > 0 && Number.isFinite(m) && e >= m;
}

/** After Stop, ignore a late TAB_CAPTURE_STARTED / ERROR from the previous start. */
export function shouldApplyTabCaptureLifecycle({ listenPhase = 'idle', isCopilotListening = false } = {}) {
  return listenPhase === 'starting' || listenPhase === 'live' || Boolean(isCopilotListening);
}

export function tabCaptureGetMediaStreamIdOptions(tabId) {
  return tabId != null ? { targetTabId: tabId } : {};
}

export async function requestTabCaptureStreamId(tabCaptureApi, tabId) {
  if (typeof tabCaptureApi?.getMediaStreamId !== 'function') return null;
  try {
    const id = await tabCaptureApi.getMediaStreamId(tabCaptureGetMediaStreamIdOptions(tabId));
    return id || null;
  } catch {
    return null;
  }
}

/**
 * Tab capture requires a video track in getUserMedia (Chrome sample), but that
 * track ending must not stop the copilot. Only lost tab *audio* ends the session.
 */
export function isSessionEndingCaptureTrack(track) {
  return Boolean(track && track.kind === 'audio');
}

export function applyTranscriptUpdate(state, { text, isFinal, words, audioChannel, lang } = {}) {
  const t = strings(lang);
  const finalTranscript = state.finalTranscript || '';
  const finalWords = Array.isArray(state.finalWords) ? state.finalWords : [];
  const prospectFinal = state.prospectFinal || '';
  const prospectInterim = state.prospectInterim || '';
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
    const nextFinal = tagged
      ? (finalTranscript ? `${finalTranscript} ${tagged}` : tagged)
      : finalTranscript;
    const extra = Array.isArray(words) ? words.filter((w) => w && w.text) : [];
    const nextProspectFinal =
      role === 'rep'
        ? prospectFinal
        : piece
          ? (prospectFinal ? `${prospectFinal} ${piece}` : piece)
          : prospectFinal;
    return {
      finalTranscript: nextFinal,
      interimTranscript: '',
      prospectFinal: nextProspectFinal,
      prospectInterim: role === 'rep' ? prospectInterim : '',
      finalWords: extra.length ? finalWords.concat(extra) : finalWords,
    };
  }

  if (role === 'rep') {
    return {
      finalTranscript,
      interimTranscript: tagged,
      prospectFinal,
      prospectInterim,
      finalWords,
    };
  }

  return {
    finalTranscript,
    interimTranscript: tagged || piece,
    prospectFinal,
    prospectInterim: piece,
    finalWords,
  };
}
