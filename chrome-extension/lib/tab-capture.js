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
} = {}) {
  if (isCopilotListening) return { ok: false, reason: 'already_listening' };
  if (isRecording) return { ok: false, reason: 'mic_recording' };
  if (!hasToken) return { ok: false, reason: 'login_required' };
  if (tabId == null && !hasStreamId) return { ok: false, reason: 'no_tab' };
  return { ok: true };
}

export function startDeniedMessage(reason) {
  switch (reason) {
    case 'mic_recording':
      return 'Stop the voice memo before listening to this tab.';
    case 'already_listening':
      return 'Already listening to a tab.';
    case 'login_required':
      return 'Log in above to start listening.';
    case 'no_tab':
      return 'Focus a Chrome tab and try again.';
    case 'no_stream_id':
      return 'Could not capture this tab. Focus the call tab and click Listen again.';
    case 'not_hubspot_tab':
      return 'Open the HubSpot record where the call is happening, then click Listen.';
    case 'unsupported_meeting_tab':
      return 'Listen captures a HubSpot call tab in Chrome — not Zoom, Meet, or Teams desktop.';
    case 'no_audio':
      return 'This tab has no audio yet. Start the call, then click Listen again.';
    case 'stream_expired':
      return 'Capture expired before it started. Click Listen again.';
    case 'capture_failed':
      return 'Could not start tab audio. Stay on the HubSpot call tab and click Listen again.';
    default:
      return 'Could not start tab capture.';
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
  listenPhase = null,
  isCopilotListening = false,
  copilotError = null,
  tabTitle = null,
  heardAnything = false,
} = {}) {
  const phase = resolveListenPhase({ listenPhase, isCopilotListening, copilotError });
  switch (phase) {
    case 'starting':
      return {
        phase: 'starting',
        buttonLabel: 'Starting…',
        statusLabel: 'Starting',
        header: 'Starting listen',
        line: 'Capturing this tab’s audio…',
        live: false,
      };
    case 'live':
      return {
        phase: 'live',
        buttonLabel: 'Stop listening',
        statusLabel: heardAnything ? 'Listening' : 'Listening — waiting for speech',
        header: tabTitle ? `Listening · ${tabTitle}` : 'Listening to this tab',
    line: heardAnything
      ? (tabTitle ? `Hearing “${tabTitle}”` : 'Hearing this tab')
      : 'Hearing this tab, not your mic. The other side of the call should appear here.',
        live: true,
      };
    case 'error':
      return {
        phase: 'error',
        buttonLabel: 'Listen to tab',
        statusLabel: 'Not listening',
        header: 'Ready to record',
        line: copilotError || startDeniedMessage('capture_failed'),
        live: false,
      };
    default:
      return {
        phase: 'idle',
        buttonLabel: 'Listen to tab',
        statusLabel: 'Record',
        header: 'Ready to record',
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

export function applyTranscriptUpdate(state, { text, isFinal, words, audioChannel } = {}) {
  const finalTranscript = state.finalTranscript || '';
  const finalWords = Array.isArray(state.finalWords) ? state.finalWords : [];
  const prospectFinal = state.prospectFinal || '';
  const prospectInterim = state.prospectInterim || '';
  const piece = typeof text === 'string' ? text : '';
  const role = audioChannel === 'rep' ? 'rep' : audioChannel === 'prospect' ? 'prospect' : null;
  const tagged = !piece
    ? ''
    : role === 'rep'
      ? `You: ${piece}`
      : role === 'prospect'
        ? `Them: ${piece}`
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
