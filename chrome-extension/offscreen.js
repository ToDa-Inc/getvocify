/**
 * Offscreen Document - Mic memos + tab-capture copilot
 *
 * Tab capture follows Chrome’s MV3 sample:
 * getMediaStreamId (service worker) → getUserMedia chromeMediaSource:"tab" here
 * → AudioContext.destination so the tab is not muted.
 * https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture
 */

import { CALL_STATES } from './lib/dialer.js';
import { startLocalRingback as playLocalRingback } from './lib/local-ringback.js';
import {
  isCarrierHangupError,
  isVoiceAccessTokenError,
  isVoiceSdkGeneralError,
  userFacingCallError,
} from './lib/call-format.js';
import { isListenEpochCurrent, isSessionEndingCaptureTrack, tabCaptureGetUserMediaConstraints } from './lib/tab-capture.js';
import { applyChannelLabelsToLiveUrl, encodeChannelAudio } from './lib/stt-channels.js';
import { api } from './lib/api.js';
import { LOCAL_API_BASE, apiBaseToWsOrigin } from './lib/api-base.js';
import { telnyxHangupMessage, vocifyCallHeaders } from './lib/telnyx-headers.js';
import { cloneAudioStream } from './lib/media-stream.js';

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
let telnyxClient = null;
let activeCall = null;
let activeCallProvider = null;
let telnyxMuted = false;
let lastReportedCallState = null;
let stream = null;
let recorderStream = null;
let pcmStream = null;
let micStartedAt = 0;
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

function stopOwnedTracks() {
  [stream, recorderStream, pcmStream].forEach((owned) => {
    if (!owned) return;
    owned.getTracks().forEach((track) => {
      try { track.stop(); } catch (_) { /* already ended */ }
    });
  });
  stream = null;
  recorderStream = null;
  pcmStream = null;
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

  if (stopTracks) stopOwnedTracks();
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
    recorderStream = cloneAudioStream(stream);
    pcmStream = cloneAudioStream(stream);

    const recorderOptions = { mimeType: 'audio/webm;codecs=opus' };
    if (!MediaRecorder.isTypeSupported(recorderOptions.mimeType)) {
      delete recorderOptions.mimeType;
    }
    mediaRecorder = new MediaRecorder(recorderStream, recorderOptions);
    audioChunks = [];
    micStartedAt = Date.now();

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) audioChunks.push(event.data);
    };

    mediaRecorder.onstop = () => {
      const durationMs = micStartedAt ? Date.now() - micStartedAt : 0;
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      const reader = new FileReader();
      reader.onloadend = () => {
        chrome.runtime.sendMessage({
          type: 'RECORDING_COMPLETE',
          audioData: reader.result,
          durationMs,
          byteLength: audioBlob.size,
        });
      };
      reader.readAsDataURL(audioBlob);
      stopOwnedTracks();
    };

    try {
      await connectPcmSocket(pcmStream, wsUrl);
    } catch (sttError) {
      console.warn('[Offscreen] Live STT failed; mic recording continues', sttError);
    }
    if (captureMode !== 'mic' || !mediaRecorder) return;
    mediaRecorder.start(1000);

    chrome.runtime.sendMessage({ type: 'RECORDING_STARTED' });
    console.log('[Offscreen] Recording started');
  } catch (error) {
    console.error('[Offscreen] Recording error:', error);
    captureMode = null;
    stopOwnedTracks();
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

function twilioErrorText(err, fallback = 'No se pudo iniciar la llamada.') {
  return userFacingCallError(err, fallback);
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

function destroyTwilioDevice() {
  const device = twilioDevice;
  twilioDevice = null;
  if (!device) return;
  try {
    device.destroy();
  } catch (_) { /* already gone */ }
}

function attachDeviceListeners(device) {
  device.on('error', (err) => {
    if (
      isCarrierHangupError(err)
      || isCarrierHangupError(twilioErrorText(err, ''))
      || isVoiceSdkGeneralError(err)
      || isVoiceSdkGeneralError(err?.message)
    ) {
      return;
    }
    activeCall = null;
    activeCallProvider = null;
    if (isVoiceAccessTokenError(err) && twilioDevice === device) {
      destroyTwilioDevice();
    } else {
      try {
        device.destroy();
      } catch (_) { /* already gone */ }
      if (twilioDevice === device) twilioDevice = null;
    }
    reportCallState(CALL_STATES.IDLE, twilioErrorText(err, 'No se pudo iniciar la llamada.'));
  });
  device.on('tokenWillExpire', () => {
    chrome.runtime.sendMessage({ type: 'CALL_TOKEN_REFRESH_REQUEST' });
  });
}

function ensureDevice(token, { forceNew = false } = {}) {
  if (forceNew) destroyTwilioDevice();
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

function requestCallTokenRefresh() {
  chrome.runtime.sendMessage({ type: 'CALL_TOKEN_REFRESH_REQUEST' });
}

function isTelnyxAuthError(err) {
  const code = Number(err?.code ?? err?.error?.code);
  if (code === 34001 || code === 46001 || code === 46002 || code === 46003) return true;
  const msg = String(err?.message || err?.error?.message || '');
  return /unauthor|invalid (token|credent)|login failed|authentication/i.test(msg);
}

function telnyxCallSid(call) {
  return call?.telnyxIDs?.telnyxCallControlId || call?.id || null;
}

function telnyxErrorText(err, fallback = 'Error de llamada') {
  if (!err) return fallback;
  const code = err.code != null ? String(err.code) : '';
  const msg = err.message || err.error?.message || fallback;
  return code && !String(msg).includes(code) ? `${code} ${msg}` : msg;
}

function destroyTelnyxClient(client) {
  try {
    client?.disconnect?.();
  } catch (_) { /* already gone */ }
  if (telnyxClient === client) telnyxClient = null;
}

function attachTelnyxClientListeners(client) {
  client.on('telnyx.warning', (warning) => {
    const payload = warning?.warning || warning;
    if (isTelnyxAuthError(payload) || payload?.code === 34001) {
      requestCallTokenRefresh();
    }
  });
  client.on('telnyx.error', (err) => {
    if (isTelnyxAuthError(err)) requestCallTokenRefresh();
    if (lastReportedCallState && lastReportedCallState !== CALL_STATES.IDLE) {
      activeCall = null;
      activeCallProvider = null;
      reportCallState(CALL_STATES.IDLE, telnyxErrorText(err, 'Error de dispositivo'));
      destroyTelnyxClient(client);
    }
  });
  client.on('telnyx.notification', (notification) => {
    if (notification?.type !== 'callUpdate' || !notification.call) return;
    if (activeCall && notification.call.id && activeCall.id && notification.call.id !== activeCall.id) {
      return;
    }
    mapTelnyxCallState(notification.call);
  });
}

function mapTelnyxCallState(call) {
  const sid = telnyxCallSid(call);
  const state = String(call?.state || '').toLowerCase();
  if (state === 'active' || state === 'held') {
    // Park answers the WebRTC leg immediately; PSTN is still ringing.
    reportCallState(CALL_STATES.RINGING, null, { callSid: sid, muted: telnyxMuted });
    return;
  }
  if (['ringing', 'early', 'trying', 'requesting', 'recovering'].includes(state)) {
    reportCallState(CALL_STATES.RINGING, null, { callSid: sid });
    return;
  }
  if (['hangup', 'destroy', 'destroyed', 'purge'].includes(state)) {
    const ended = telnyxHangupMessage(call);
    activeCall = null;
    activeCallProvider = null;
    stopLocalRingback();
    reportCallState(CALL_STATES.IDLE, ended);
    destroyTelnyxClient(telnyxClient);
  }
}

function ensureTelnyxRemote() {
  return document.getElementById('telnyx-remote')
    || document.body.appendChild(Object.assign(document.createElement('audio'), {
      id: 'telnyx-remote',
      autoplay: true,
    }));
}

async function startCall({ token, to, callerId, contactId, dealId, provider, skipLocalRingback }) {
  if (provider === 'telnyx') {
    return startTelnyxCall({ token, to, callerId, contactId, dealId, skipLocalRingback });
  }
  stopLocalRingback();
  return startTwilioCall({ token, to, callerId, contactId, dealId });
}

async function startTelnyxCall({ token, to, callerId, contactId, dealId, skipLocalRingback }) {
  if (!skipLocalRingback) ensureLocalRingback();
  try {
    const TelnyxRTC = globalThis.TelnyxWebRTC?.TelnyxRTC;
    if (!TelnyxRTC) throw new Error('Telnyx WebRTC SDK no cargado');

    if (telnyxClient) destroyTelnyxClient(telnyxClient);

    const client = new TelnyxRTC({
      login_token: token,
      ringbackFile: chrome.runtime?.getURL?.('call-ringback.wav') || 'call-ringback.wav',
    });
    telnyxClient = client;
    attachTelnyxClientListeners(client);

    await new Promise((resolve, reject) => {
      let settled = false;
      const onReady = () => {
        if (settled) return;
        settled = true;
        resolve();
      };
      const onError = (err) => {
        if (isTelnyxAuthError(err)) requestCallTokenRefresh();
        if (settled) return;
        settled = true;
        reject(err);
      };
      client.on('telnyx.ready', onReady);
      client.on('telnyx.error', onError);
      client.connect();
    });

    reportCallState(CALL_STATES.CONNECTING);
    telnyxMuted = false;
    activeCallProvider = 'telnyx';
    if (!skipLocalRingback) ensureLocalRingback();

    const remote = ensureTelnyxRemote();
    watchRemoteAudio(remote, () => {
      // Park answers WebRTC immediately; remote audio is not PSTN answered.
      stopLocalRingback();
    });
    const call = client.newCall({
      destinationNumber: to,
      audio: true,
      remoteElement: remote,
      customHeaders: vocifyCallHeaders({ callerId, contactId, dealId }),
    });
    activeCall = call;
    const callSid = telnyxCallSid(call);
    reportCallState(CALL_STATES.CONNECTING, null, { callSid });
    if (typeof call.on === 'function') {
      call.on('telnyx.notification', (notification) => {
        if (notification?.call) mapTelnyxCallState(notification.call);
      });
    }
  } catch (error) {
    stopLocalRingback();
    activeCall = null;
    activeCallProvider = null;
    destroyTelnyxClient(telnyxClient);
    reportCallState(CALL_STATES.IDLE, telnyxErrorText(error, error.message || 'No se pudo iniciar la llamada'));
  }
}

async function connectTwilioDevice({ token, to, callerId, contactId, dealId, forceNew = false }) {
  if (!globalThis.Twilio?.Device) {
    throw new Error('Twilio Voice SDK no cargado');
  }
  const device = ensureDevice(token, { forceNew });
  activeCallProvider = 'twilio';

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
    activeCallProvider = null;
    reportCallState(CALL_STATES.IDLE);
  });
  activeCall.on('cancel', () => {
    activeCall = null;
    activeCallProvider = null;
    reportCallState(CALL_STATES.IDLE);
  });
  activeCall.on('error', (err) => {
    activeCall = null;
    activeCallProvider = null;
    if (isVoiceAccessTokenError(err)) destroyTwilioDevice();
    reportCallState(CALL_STATES.IDLE, twilioErrorText(err, 'No se pudo iniciar la llamada.'));
  });
}

async function startTwilioCall({ token, to, callerId, contactId, dealId }) {
  try {
    await connectTwilioDevice({ token, to, callerId, contactId, dealId });
  } catch (error) {
    if (isVoiceAccessTokenError(error)) {
      try {
        await connectTwilioDevice({ token, to, callerId, contactId, dealId, forceNew: true });
        return;
      } catch (retryErr) {
        error = retryErr;
      }
    }
    activeCall = null;
    activeCallProvider = null;
    if (isVoiceAccessTokenError(error)) destroyTwilioDevice();
    reportCallState(CALL_STATES.IDLE, twilioErrorText(error, error.message || 'No se pudo iniciar la llamada.'));
  }
}

let stopRingbackFn = null;

function watchRemoteAudio(remote, onAudio) {
  let stopped = false;
  let loudFrames = 0;
  const data = new Uint8Array(256);
  const hook = () => {
    if (stopped) return;
    const stream = remote.srcObject;
    if (!(stream instanceof MediaStream)) {
      setTimeout(hook, 150);
      return;
    }
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const tick = () => {
      if (stopped) return;
      analyser.getByteTimeDomainData(data);
      let peak = 0;
      for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
      if (peak > 20) {
        loudFrames += 1;
        if (loudFrames >= 12) {
          stopped = true;
          onAudio();
          return;
        }
      } else {
        loudFrames = 0;
      }
      requestAnimationFrame(tick);
    };
    tick();
  };
  hook();
}

function ensureLocalRingback() {
  if (stopRingbackFn) return;
  stopRingbackFn = playLocalRingback();
}

function startLocalRingback() {
  ensureLocalRingback();
}

function stopLocalRingback() {
  stopRingbackFn?.();
  stopRingbackFn = null;
}

function hangupCall() {
  stopLocalRingback();
  reportCallState(CALL_STATES.ENDING);
  try {
    if (activeCallProvider === 'telnyx') {
      // Do not disconnect the client here — that drops the SIP BYE
      // before Telnyx can tear down the parked/PSTN legs.
      activeCall?.hangup?.();
    } else if (activeCall) {
      activeCall.disconnect();
    }
  } catch (_) {
    /* already gone */
  }
  activeCall = null;
  activeCallProvider = null;
  reportCallState(CALL_STATES.IDLE);
}

function muteCall(muted) {
  if (!activeCall) return;
  const next = Boolean(muted);
  if (activeCallProvider === 'telnyx') {
    if (next) activeCall.muteAudio?.();
    else activeCall.unmuteAudio?.();
    telnyxMuted = next;
    reportCallState(lastReportedCallState || CALL_STATES.ACTIVE, null, {
      muted: telnyxMuted,
      callSid: telnyxCallSid(activeCall),
    });
    return;
  }
  activeCall.mute(next);
  reportCallState(lastReportedCallState || CALL_STATES.ACTIVE, null, {
    muted: Boolean(activeCall.isMuted()),
    callSid: activeCall.parameters?.CallSid || null,
  });
}

function sendDigits(digits) {
  if (!activeCall) return;
  if (!/^[0-9*#]+$/.test(String(digits || ''))) return;
  if (activeCallProvider === 'telnyx') {
    activeCall.dtmf?.(digits);
    return;
  }
  activeCall.sendDigits(digits);
}

function updateToken(token, provider) {
  if (!token) return;
  if (provider === 'telnyx' || telnyxClient) {
    telnyxClient?.login?.({ creds: { login_token: token } });
    return;
  }
  if (twilioDevice) twilioDevice.updateToken(token);
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

  if (mode === 'mic' && mediaRecorder && mediaRecorder.state !== 'inactive') {
    tearDownGraph({ stopTracks: false });
    const rec = mediaRecorder;
    mediaRecorder = null;
    try {
      if (rec.state === 'recording') rec.requestData();
      rec.stop();
    } catch (error) {
      chrome.runtime.sendMessage({
        type: 'RECORDING_ERROR',
        error: error.message || 'Failed to stop recording.',
      });
      stopOwnedTracks();
    }
    return;
  }

  tearDownGraph({ stopTracks: true });
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
    case 'START_RINGBACK':
      startLocalRingback();
      break;
    case 'STOP_RINGBACK':
      stopLocalRingback();
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
      updateToken(message.token, message.provider);
      break;
    case 'DESTROY_VOICE_DEVICE':
      destroyTwilioDevice();
      break;
  }
});
