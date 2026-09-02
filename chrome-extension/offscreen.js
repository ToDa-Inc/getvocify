/**
 * Offscreen Document - Mic memos + tab-capture copilot
 *
 * Tab capture follows Chrome’s MV3 sample:
 * getMediaStreamId (service worker) → getUserMedia chromeMediaSource:"tab" here
 * → AudioContext.destination so the tab is not muted.
 * https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture
 */

import { CALL_STATES } from './lib/dialer.js';
import { isListenEpochCurrent, isSessionEndingCaptureTrack, tabCaptureGetUserMediaConstraints } from './lib/tab-capture.js';
import { applyChannelLabelsToLiveUrl, encodeChannelAudio } from './lib/stt-channels.js';
import { api } from './lib/api.js';
import { LOCAL_API_BASE, apiBaseToWsOrigin } from './lib/api-base.js';

async function defaultWsUrl() {
  try {
    const apiBase = await api.getApiBase();
    return `${apiBaseToWsOrigin(apiBase)}/api/v1/transcription/live?language=multi`;
  } catch {
    return `${apiBaseToWsOrigin(LOCAL_API_BASE)}/api/v1/transcription/live?language=multi`;
  }
}

let mediaRecorder = null;
let audioChunks = [];
let twilioDevice = null;
let activeCall = null;
let lastReportedCallState = null;
let stream = null;
let audioContext = null;
let playbackContext = null;
let workletNode = null;
let websocket = null;
/** 'mic' | 'tab' — mic uploads a blob; tab capture does not. */
let captureMode = null;
/** Offscreen starts with epoch N are cancelled when Stop raises minEpoch above N. */
let tabListenMinEpoch = 0;

function forwardTranscriptMessage(data) {
  if (data.type === 'connected') return;

  if (data.type === 'EndOfUtterance') {
    chrome.runtime.sendMessage({
      type: 'END_OF_UTTERANCE',
      audioChannel: data.audio_channel || null,
    });
    return;
  }

  if (data.type === 'Results') {
    const transcript = data.channel?.alternatives?.[0]?.transcript || '';
    const isFinal = data.is_final || data.speech_final;
    const words = Array.isArray(data.words) ? data.words : [];
    if (!transcript && words.length === 0) return;
    chrome.runtime.sendMessage({
      type: 'TRANSCRIPT_UPDATE',
      text: transcript,
      isFinal,
      words,
      audioChannel: data.audio_channel || null,
      provider: data.provider || 'speechmatics',
    });
  }
}

function hookPcmWorklet(mediaStream, onFrame) {
  const source = audioContext.createMediaStreamSource(mediaStream);
  const node = new AudioWorkletNode(audioContext, 'pcm-processor', { processorOptions: {} });
  node.port.onmessage = (e) => {
    if (e.data) onFrame(e.data);
  };
  source.connect(node);
  const silence = audioContext.createGain();
  silence.gain.value = 0;
  node.connect(silence);
  silence.connect(audioContext.destination);
  return node;
}

async function connectPcmSocket(mediaStream, wsUrl) {
  const url = wsUrl || await defaultWsUrl();
  websocket = new WebSocket(url);

  websocket.onopen = () => {
    console.log('[Offscreen] WebSocket connected to backend');
  };

  websocket.onmessage = (event) => {
    try {
      forwardTranscriptMessage(JSON.parse(event.data));
    } catch (e) {
      console.error('[Offscreen] Error parsing message:', e);
    }
  };

  websocket.onerror = (error) => {
    console.error('[Offscreen] WebSocket error:', error);
  };

  websocket.onclose = () => {
    console.log('[Offscreen] WebSocket closed');
  };

  audioContext = new AudioContext({ sampleRate: 16000 });
  await audioContext.audioWorklet.addModule(chrome.runtime.getURL('audio-processor.js'));
  workletNode = hookPcmWorklet(mediaStream, (pcm) => {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.send(pcm);
    }
  });
}

async function connectChannelSockets(tabStream, wsUrl) {
  const url = applyChannelLabelsToLiveUrl(wsUrl || await defaultWsUrl(), ['prospect']);
  websocket = new WebSocket(url);

  websocket.onopen = () => {
    console.log('[Offscreen] Channel WebSocket connected prospect');
  };

  websocket.onmessage = (event) => {
    try {
      forwardTranscriptMessage(JSON.parse(event.data));
    } catch (e) {
      console.error('[Offscreen] Error parsing message:', e);
    }
  };

  websocket.onerror = (error) => {
    console.error('[Offscreen] WebSocket error:', error);
  };

  websocket.onclose = () => {
    console.log('[Offscreen] WebSocket closed');
  };

  audioContext = new AudioContext({ sampleRate: 16000 });
  await audioContext.audioWorklet.addModule(chrome.runtime.getURL('audio-processor.js'));

  workletNode = hookPcmWorklet(tabStream, (pcm) => {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.send(encodeChannelAudio('prospect', pcm));
    }
  });
}

async function startLabeledTabListen(tabStream, wsUrl) {
  loopTabAudioToSpeakers(tabStream);
  watchCaptureEnded(tabStream);
  await connectChannelSockets(tabStream, wsUrl);
}

function watchCaptureEnded(mediaStream) {
  mediaStream.getTracks().forEach((track) => {
    if (!isSessionEndingCaptureTrack(track)) return;
    track.onended = () => {
      if (captureMode !== 'tab') return;
      captureMode = null;
      tearDownGraph({ stopTracks: true });
      chrome.runtime.sendMessage({ type: 'TAB_CAPTURE_STOPPED' });
    };
  });
}

function loopTabAudioToSpeakers(mediaStream) {
  // chrome.tabCapture: capturing a tab mutes it unless we play the stream locally.
  playbackContext = new AudioContext();
  const playbackSource = playbackContext.createMediaStreamSource(mediaStream);
  playbackSource.connect(playbackContext.destination);
}

function tearDownGraph({ stopTracks = true } = {}) {
  if (workletNode) {
    workletNode.disconnect();
    workletNode = null;
  }

  if (websocket) {
    if (websocket.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify({ type: 'CloseStream' }));
    }
    websocket.close();
    websocket = null;
  }

  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }

  if (playbackContext) {
    playbackContext.close();
    playbackContext = null;
  }

  if (stopTracks && stream) {
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }
}

async function startRecording(wsUrl) {
  try {
    captureMode = 'mic';
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const recorderOptions = { mimeType: 'audio/webm;codecs=opus' };
    if (!MediaRecorder.isTypeSupported(recorderOptions.mimeType)) {
      delete recorderOptions.mimeType;
    }
    mediaRecorder = new MediaRecorder(stream, recorderOptions);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) audioChunks.push(event.data);
    };

    mediaRecorder.onstop = () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      const reader = new FileReader();
      reader.onloadend = () => {
        chrome.runtime.sendMessage({
          type: 'RECORDING_COMPLETE',
          audioData: reader.result,
        });
      };
      reader.readAsDataURL(audioBlob);

      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
        stream = null;
      }
    };

    await connectPcmSocket(stream, wsUrl);
    mediaRecorder.start(100);

    chrome.runtime.sendMessage({ type: 'RECORDING_STARTED' });
    console.log('[Offscreen] Recording started');
  } catch (error) {
    console.error('[Offscreen] Recording error:', error);
    captureMode = null;
    const denied = error.name === 'NotAllowedError' || /permission/i.test(error.message || '');
    chrome.runtime.sendMessage({
      type: 'RECORDING_ERROR',
      error: error.message || 'Failed to start recording. Check mic permissions.',
      openSetup: denied,
    });
  }
}

async function startTabCapture(streamId, wsUrl, epoch) {
  const startEpoch = Number(epoch) || 0;
  if (!isListenEpochCurrent(startEpoch, tabListenMinEpoch)) return;
  try {
    captureMode = 'tab';
    const nextStream = await navigator.mediaDevices.getUserMedia(
      tabCaptureGetUserMediaConstraints(streamId)
    );
    if (!isListenEpochCurrent(startEpoch, tabListenMinEpoch)) {
      nextStream.getTracks().forEach((t) => t.stop());
      return;
    }
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
    }
    stream = nextStream;
    if (!stream.getAudioTracks().length) {
      stream.getTracks().forEach((t) => t.stop());
      stream = null;
      throw new Error('This tab has no audio to capture.');
    }
    await startLabeledTabListen(stream, wsUrl);
    if (!isListenEpochCurrent(startEpoch, tabListenMinEpoch)) {
      tearDownGraph();
      captureMode = null;
      return;
    }
    chrome.runtime.sendMessage({ type: 'TAB_CAPTURE_STARTED', epoch: startEpoch });
    console.log('[Offscreen] Tab capture started');
  } catch (error) {
    if (!isListenEpochCurrent(startEpoch, tabListenMinEpoch)) return;
    console.error('[Offscreen] Tab capture error:', error);
    tearDownGraph();
    captureMode = null;
    chrome.runtime.sendMessage({
      type: 'TAB_CAPTURE_ERROR',
      error: error.message || 'Failed to capture tab audio.',
      epoch: startEpoch,
    });
  }
}

function reportCallState(state, error, extra) {
  lastReportedCallState = state;
  chrome.runtime.sendMessage({
    type: 'CALL_STATE',
    state,
    error: error || null,
    ...(extra && typeof extra === 'object' ? extra : {}),
  });
}

function attachDeviceListeners(device) {
  device.on('error', (err) => {
    activeCall = null;
    reportCallState(CALL_STATES.IDLE, err?.message || 'Error de dispositivo');
    try {
      device.destroy();
    } catch (_) { /* already gone */ }
    if (twilioDevice === device) twilioDevice = null;
  });
  device.on('tokenWillExpire', () => {
    chrome.runtime.sendMessage({ type: 'CALL_TOKEN_REFRESH_REQUEST' });
  });
}

function ensureDevice(token) {
  if (twilioDevice) {
    twilioDevice.updateToken(token);
    return twilioDevice;
  }
  twilioDevice = new globalThis.Twilio.Device(token, {
    codecPreferences: ['opus', 'pcmu'],
    logLevel: 'warn',
  });
  attachDeviceListeners(twilioDevice);
  return twilioDevice;
}

async function startCall({ token, to, callerId, contactId, dealId }) {
  try {
    if (!globalThis.Twilio?.Device) {
      throw new Error('Twilio Voice SDK no cargado');
    }
    const device = ensureDevice(token);

    reportCallState(CALL_STATES.CONNECTING);

    // `To` and `CallerId` reach the TwiML App's Voice URL as POST params.
    // CallerId is only a preference — the backend authorizes it.
    activeCall = await device.connect({
      params: {
        To: to,
        CallerId: callerId,
        ContactId: contactId || '',
        DealId: dealId || '',
      },
    });

    const callSid = activeCall.parameters?.CallSid || null;
    reportCallState(CALL_STATES.CONNECTING, null, { callSid });

    activeCall.on('ringing', () => reportCallState(CALL_STATES.RINGING, null, { callSid }));
    activeCall.on('accept', () => {
      reportCallState(CALL_STATES.ACTIVE, null, {
        callSid: activeCall?.parameters?.CallSid || callSid,
        answeredAt: Date.now(),
        muted: Boolean(activeCall?.isMuted?.()),
      });
    });
    activeCall.on('disconnect', () => {
      activeCall = null;
      reportCallState(CALL_STATES.IDLE);
    });
    activeCall.on('cancel', () => {
      activeCall = null;
      reportCallState(CALL_STATES.IDLE);
    });
    activeCall.on('error', (err) => {
      activeCall = null;
      reportCallState(CALL_STATES.IDLE, err?.message || 'Error de llamada');
    });
  } catch (error) {
    activeCall = null;
    reportCallState(CALL_STATES.IDLE, error.message || 'No se pudo iniciar la llamada');
  }
}

function hangupCall() {
  reportCallState(CALL_STATES.ENDING);
  try {
    if (activeCall) activeCall.disconnect();
  } catch (_) {
    /* already gone */
  }
  activeCall = null;
  reportCallState(CALL_STATES.IDLE);
}

function muteCall(muted) {
  if (!activeCall) return;
  activeCall.mute(Boolean(muted));
  reportCallState(lastReportedCallState || CALL_STATES.ACTIVE, null, {
    muted: Boolean(activeCall.isMuted()),
    callSid: activeCall.parameters?.CallSid || null,
  });
}

function sendDigits(digits) {
  if (!activeCall) return;
  if (!/^[0-9*#]+$/.test(String(digits || ''))) return;
  activeCall.sendDigits(digits);
}

function updateToken(token) {
  if (twilioDevice && token) twilioDevice.updateToken(token);
}

function stopRecording(minEpoch) {
  console.log('[Offscreen] Stopping recording...');
  if (minEpoch != null && Number.isFinite(Number(minEpoch))) {
    tabListenMinEpoch = Math.max(tabListenMinEpoch, Number(minEpoch));
  } else {
    tabListenMinEpoch += 1;
  }
  const mode = captureMode;
  captureMode = null;

  tearDownGraph({ stopTracks: mode !== 'mic' });

  if (mode === 'mic' && mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
    mediaRecorder = null;
    return;
  }

  mediaRecorder = null;
  if (mode === 'tab') {
    chrome.runtime.sendMessage({ type: 'TAB_CAPTURE_STOPPED' });
  }
}

chrome.runtime.onMessage.addListener((message) => {
  if (message.target !== 'offscreen') return;

  switch (message.type) {
    case 'START_RECORDING':
      startRecording(message.wsUrl);
      break;
    case 'START_TAB_CAPTURE':
      startTabCapture(message.streamId, message.wsUrl, message.epoch);
      break;
    case 'STOP_RECORDING':
    case 'STOP_TAB_CAPTURE':
      stopRecording(message.minEpoch);
      break;
    case 'START_CALL':
      startCall(message);
      break;
    case 'HANGUP_CALL':
      hangupCall();
      break;
    case 'MUTE_CALL':
      muteCall(message.muted);
      break;
    case 'SEND_DIGITS':
      sendDigits(message.digits);
      break;
    case 'UPDATE_TOKEN':
      updateToken(message.token);
      break;
  }
});
