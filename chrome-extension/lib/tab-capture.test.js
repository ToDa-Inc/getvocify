import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  applyTranscriptUpdate,
  canStartTabCapture,
  classifyTabCaptureUrl,
  isListenSessionActive,
  isListenEpochCurrent,
  isSessionEndingCaptureTrack,
  LISTEN_CLICK_MUST_NOT_AWAIT,
  listenClickRuntimeMessage,
  listenFailureReason,
  listenReasonFromOffscreenError,
  listenUiModel,
  requestTabCaptureStreamId,
  resolveListenPhase,
  shouldApplyTabCaptureLifecycle,
  startDeniedMessage,
  tabCaptureGetMediaStreamIdOptions,
  tabCaptureGetUserMediaConstraints,
  tabCaptureOffscreenReasons,
  tabCaptureStartSequence,
} from './tab-capture.js';

describe('canStartTabCapture', () => {
  it('allows listen when idle, signed in, and a tab is targeted', () => {
    assert.deepEqual(
      canStartTabCapture({
        isRecording: false,
        isCopilotListening: false,
        hasToken: true,
        tabId: 42,
      }),
      { ok: true }
    );
  });

  it('blocks listen during an active call', () => {
    const decision = canStartTabCapture({
      isRecording: false,
      isCopilotListening: false,
      hasToken: true,
      tabId: 42,
      callState: 'active',
    });
    assert.equal(decision.ok, false);
    assert.equal(decision.reason, 'call_in_progress');
  });

  it('blocks listen during a mic memo recording', () => {
    const decision = canStartTabCapture({
      isRecording: true,
      isCopilotListening: false,
      hasToken: true,
      tabId: 42,
    });
    assert.equal(decision.ok, false);
    assert.equal(decision.reason, 'mic_recording');
  });

  it('blocks a second listen session', () => {
    const decision = canStartTabCapture({
      isRecording: false,
      isCopilotListening: true,
      hasToken: true,
      tabId: 42,
    });
    assert.equal(decision.ok, false);
    assert.equal(decision.reason, 'already_listening');
  });

  it('requires login', () => {
    const decision = canStartTabCapture({
      isRecording: false,
      isCopilotListening: false,
      hasToken: false,
      tabId: 42,
    });
    assert.equal(decision.ok, false);
    assert.equal(decision.reason, 'login_required');
  });

  it('requires a target tab', () => {
    const decision = canStartTabCapture({
      isRecording: false,
      isCopilotListening: false,
      hasToken: true,
      tabId: null,
    });
    assert.equal(decision.ok, false);
    assert.equal(decision.reason, 'no_tab');
  });

  it('allows a missing tab id when the Listen click already produced a stream id', () => {
    assert.deepEqual(
      canStartTabCapture({
        isRecording: false,
        isCopilotListening: false,
        hasToken: true,
        tabId: null,
        hasStreamId: true,
      }),
      { ok: true }
    );
  });
});

describe('startDeniedMessage', () => {
  it('explains a missing stream id without sending the user to the offscreen picker', () => {
    assert.match(startDeniedMessage('no_stream_id'), /Focus the call tab/i);
  });

  it('asks the user to hang up before listening during a call', () => {
    assert.match(startDeniedMessage('call_in_progress'), /Hang up the call/i);
  });

  it('names Zoom/Meet/Teams as unsupported instead of failing silently', () => {
    assert.match(startDeniedMessage('unsupported_meeting_tab'), /not Zoom, Meet, or Teams/i);
  });
});

describe('listen status model', () => {
  it('treats starting and live as an active session so a second click stops', () => {
    assert.equal(isListenSessionActive('starting'), true);
    assert.equal(isListenSessionActive('live'), true);
    assert.equal(isListenSessionActive('idle'), false);
    assert.equal(isListenSessionActive('error'), false);
    assert.deepEqual(listenClickRuntimeMessage({ listenPhase: 'starting' }), {
      type: 'STOP_TAB_CAPTURE',
    });
    assert.deepEqual(listenClickRuntimeMessage({ listenPhase: 'live', commandSeq: 4 }), {
      type: 'STOP_TAB_CAPTURE',
      commandSeq: 4,
    });
  });

  it('does not claim live until capture is confirmed', () => {
    const starting = listenUiModel({ listenPhase: 'starting' });
    assert.equal(starting.phase, 'starting');
    assert.equal(starting.live, false);
    assert.match(starting.line, /Capturing/i);
    assert.equal(starting.buttonLabel, 'Starting…');
  });

  it('says listening and waiting for speech when connected with no transcript yet', () => {
    const live = listenUiModel({
      listenPhase: 'live',
      isCopilotListening: true,
      tabTitle: 'Acme deal',
      heardAnything: false,
    });
    assert.equal(live.live, true);
    assert.match(live.statusLabel, /waiting for speech/i);
    assert.match(live.line, /not your mic/i);
  });

  it('shows a not-listening error in the panel instead of hiding it', () => {
    const err = listenUiModel({
      listenPhase: 'error',
      copilotError: startDeniedMessage('no_stream_id'),
    });
    assert.equal(err.phase, 'error');
    assert.equal(err.live, false);
    assert.match(err.line, /Focus the call tab/i);
    assert.equal(err.buttonLabel, 'Listen to tab');
  });

  it('falls back to live/error when listenPhase is missing from an older state payload', () => {
    assert.equal(resolveListenPhase({ isCopilotListening: true }), 'live');
    assert.equal(resolveListenPhase({ listenPhase: 'idle', isCopilotListening: true }), 'live');
    assert.equal(resolveListenPhase({ copilotError: 'nope' }), 'error');
    assert.equal(resolveListenPhase({}), 'idle');
  });
});

describe('tab listen stop races', () => {
  it('rejects an offscreen start whose epoch was already cancelled', () => {
    assert.equal(isListenEpochCurrent(1, 1), true);
    assert.equal(isListenEpochCurrent(1, 2), false);
    assert.equal(isListenEpochCurrent(3, 2), true);
    assert.equal(isListenEpochCurrent(0, 0), false);
  });

  it('does not apply TAB_CAPTURE_STARTED after the user already stopped', () => {
    assert.equal(shouldApplyTabCaptureLifecycle({ listenPhase: 'starting' }), true);
    assert.equal(shouldApplyTabCaptureLifecycle({ listenPhase: 'live', isCopilotListening: true }), true);
    assert.equal(shouldApplyTabCaptureLifecycle({ listenPhase: 'idle' }), false);
    assert.equal(shouldApplyTabCaptureLifecycle({ listenPhase: 'error' }), false);
  });
});

describe('listenFailureReason', () => {
  it('maps a Google Meet URL to the meeting-app blocker', () => {
    assert.equal(classifyTabCaptureUrl('https://meet.google.com/abc-defg-hij').kind, 'meeting_app');
    assert.equal(
      listenFailureReason({ streamId: null, pageUrl: 'https://app.zoom.us/wc/123' }),
      'unsupported_meeting_tab'
    );
  });

  it('maps a non-HubSpot Chrome tab to a HubSpot-only hint', () => {
    assert.equal(classifyTabCaptureUrl('https://mail.google.com/').kind, 'other');
    assert.equal(
      listenFailureReason({ streamId: null, pageUrl: 'https://mail.google.com/' }),
      'not_hubspot_tab'
    );
  });

  it('keeps HubSpot missing-stream as no_stream_id so the user retries on that tab', () => {
    assert.equal(classifyTabCaptureUrl('https://app.hubspot.com/contacts/123/deal/9').kind, 'hubspot');
    assert.equal(
      listenFailureReason({
        streamId: null,
        pageUrl: 'https://app.hubspot.com/contacts/123/deal/9',
      }),
      'no_stream_id'
    );
  });

  it('maps offscreen “no audio” instead of a generic capture failure', () => {
    assert.equal(
      listenReasonFromOffscreenError('This tab has no audio to capture.'),
      'no_audio'
    );
  });
});

describe('tabCaptureGetUserMediaConstraints', () => {
  it('matches Chrome’s official tabCapture offscreen sample (audio + video, mandatory tab source)', () => {
    assert.deepEqual(tabCaptureGetUserMediaConstraints('stream-abc'), {
      audio: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: 'stream-abc',
        },
      },
      video: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: 'stream-abc',
        },
      },
    });
  });
});

describe('tabCaptureOffscreenReasons', () => {
  it('only asks for USER_MEDIA and AUDIO_PLAYBACK — Listen must not open a getDisplayMedia picker', () => {
    const reasons = tabCaptureOffscreenReasons();
    assert.deepEqual(reasons, ['USER_MEDIA', 'AUDIO_PLAYBACK']);
    assert.equal(reasons.includes('DISPLAY_MEDIA'), false);
  });
});

describe('tabCaptureStartSequence', () => {
  it('matches Chrome’s MV3 sample: offscreen, then getMediaStreamId, then offscreen getUserMedia', () => {
    assert.deepEqual(tabCaptureStartSequence(), [
      'ensure_offscreen',
      'getMediaStreamId',
      'offscreen_getUserMedia',
    ]);
  });
});

describe('listen click gesture', () => {
  it('forbids GET_STATE and tabs.query before getMediaStreamId (those consume the click)', () => {
    assert.deepEqual([...LISTEN_CLICK_MUST_NOT_AWAIT], ['GET_STATE', 'tabs.query']);
  });

  it('sends STOP immediately when already listening', () => {
    assert.deepEqual(listenClickRuntimeMessage({ isCopilotListening: true }), {
      type: 'STOP_TAB_CAPTURE',
    });
  });

  it('starts capture with the cached tab id and stream id — no extra lookups', () => {
    assert.deepEqual(
      listenClickRuntimeMessage({
        isCopilotListening: false,
        captureTabId: 42,
        streamId: 'sid-1',
      }),
      { type: 'START_TAB_CAPTURE', tabId: 42, streamId: 'sid-1' }
    );
  });
});

describe('tabCaptureGetMediaStreamIdOptions', () => {
  it('targets an explicit tab when we already know the id', () => {
    assert.deepEqual(tabCaptureGetMediaStreamIdOptions(7), { targetTabId: 7 });
  });

  it('omits targetTabId so Chrome uses the current active tab', () => {
    assert.deepEqual(tabCaptureGetMediaStreamIdOptions(null), {});
    assert.deepEqual(tabCaptureGetMediaStreamIdOptions(undefined), {});
  });
});

describe('requestTabCaptureStreamId', () => {
  it('calls getMediaStreamId with the target tab and returns the id', async () => {
    const calls = [];
    const api = {
      getMediaStreamId: async (opts) => {
        calls.push(opts);
        return 'stream-abc';
      },
    };
    const id = await requestTabCaptureStreamId(api, 9);
    assert.equal(id, 'stream-abc');
    assert.deepEqual(calls, [{ targetTabId: 9 }]);
  });

  it('returns null when the API is missing or throws', async () => {
    assert.equal(await requestTabCaptureStreamId(null, 1), null);
    assert.equal(
      await requestTabCaptureStreamId({
        getMediaStreamId: async () => {
          throw new Error('Extension has not been invoked for the current page.');
        },
      }, 1),
      null
    );
  });
});

describe('isSessionEndingCaptureTrack', () => {
  it('ends listen only when the tab audio track dies, not the unused video track', () => {
    assert.equal(isSessionEndingCaptureTrack({ kind: 'audio' }), true);
    assert.equal(isSessionEndingCaptureTrack({ kind: 'video' }), false);
    assert.equal(isSessionEndingCaptureTrack(null), false);
  });
});

describe('applyTranscriptUpdate', () => {
  it('appends finals and clears interim', () => {
    const next = applyTranscriptUpdate(
      { finalTranscript: 'hello', interimTranscript: 'wor', finalWords: [] },
      { text: 'world', isFinal: true, words: [{ text: 'world', speaker: null, is_punct: false }] }
    );
    assert.equal(next.finalTranscript, 'hello world');
    assert.equal(next.interimTranscript, '');
    assert.equal(next.finalWords.length, 1);
  });

  it('replaces interim without touching finals', () => {
    const next = applyTranscriptUpdate(
      { finalTranscript: 'hello', interimTranscript: 'w', finalWords: [] },
      { text: 'world', isFinal: false }
    );
    assert.equal(next.finalTranscript, 'hello');
    assert.equal(next.interimTranscript, 'world');
  });

  it('tags prospect vs rep on the display transcript and keeps prospect-only text for coaching', () => {
    let state = { finalTranscript: '', prospectFinal: '', prospectInterim: '', interimTranscript: '', finalWords: [] };
    state = applyTranscriptUpdate(state, {
      text: 'the price is too high for us',
      isFinal: true,
      audioChannel: 'prospect',
    });
    state = applyTranscriptUpdate(state, {
      text: 'we can start with a smaller seat count',
      isFinal: true,
      audioChannel: 'rep',
    });
    assert.equal(
      state.finalTranscript,
      'Them: the price is too high for us You: we can start with a smaller seat count'
    );
    assert.equal(state.prospectFinal, 'the price is too high for us');
  });

  it('does not put rep interim into the prospect coaching buffer', () => {
    const next = applyTranscriptUpdate(
      { finalTranscript: 'Them: hello', prospectFinal: 'hello', prospectInterim: '', interimTranscript: '' },
      { text: 'let me explain', isFinal: false, audioChannel: 'rep' }
    );
    assert.equal(next.prospectFinal, 'hello');
    assert.equal(next.prospectInterim, '');
    assert.equal(next.interimTranscript, 'You: let me explain');
  });

  it('treats unlabeled audio as prospect for the coaching buffer without adding Them/You tags', () => {
    const next = applyTranscriptUpdate(
      { finalTranscript: '', prospectFinal: '', interimTranscript: '' },
      { text: 'price is a problem for the team', isFinal: true }
    );
    assert.equal(next.finalTranscript, 'price is a problem for the team');
    assert.equal(next.prospectFinal, 'price is a problem for the team');
  });
});
