import { applyChannelLabelsToLiveUrl, encodeChannelAudio, liveTranscriptionUrl } from '../lib/channels.js';
import { pcmFromAudioBuffer } from '../lib/pcm.js';
import { applyTranscriptUpdate, canStartListen, startDeniedMessage } from '../lib/listen-policy.js';

const PROD_API = 'https://api.getvocify.com/api/v1';
const STORAGE = {
  token: 'vocify_access',
  refresh: 'vocify_refresh',
  api: 'vocify_api_base',
  email: 'vocify_email',
};

const loginPanel = document.getElementById('login-panel');
const listenPanel = document.getElementById('listen-panel');
const loginError = document.getElementById('login-error');
const listenError = document.getElementById('listen-error');
const statusEl = document.getElementById('status');
const transcriptEl = document.getElementById('transcript');
const btnListen = document.getElementById('btn-listen');
const btnStop = document.getElementById('btn-stop');

let listening = false;
let audioContext = null;
let websocket = null;
let captureStreams = [];
let processors = [];
let transcriptState = { finalTranscript: '', interimTranscript: '' };

function apiBase() {
  return (localStorage.getItem(STORAGE.api) || document.getElementById('api-base').value || PROD_API)
    .trim()
    .replace(/\/+$/, '');
}

function showError(el, message) {
  el.hidden = !message;
  el.textContent = message || '';
}

function setLoggedIn(on) {
  loginPanel.hidden = on;
  listenPanel.hidden = !on;
}

async function request(path, { method = 'GET', body, token } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${apiBase()}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return data;
}

function renderTranscript() {
  const text = `${transcriptState.finalTranscript} ${transcriptState.interimTranscript}`.trim();
  if (!text) {
    transcriptEl.innerHTML = '<p class="empty">Transcript will appear here, labeled You / Them.</p>';
    return;
  }
  const parts = text.split(/(?=(?:You|Them): )/).filter(Boolean);
  transcriptEl.innerHTML = '';
  for (const part of parts) {
    const isYou = part.startsWith('You:');
    const row = document.createElement('div');
    row.className = `turn ${isYou ? 'you' : 'them'}`;
    const speaker = document.createElement('span');
    speaker.className = 'speaker';
    speaker.textContent = isYou ? 'You' : 'Them';
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = part.replace(/^(You|Them):\s*/, '');
    row.append(speaker, bubble);
    transcriptEl.appendChild(row);
  }
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function hookPcm(ctx, stream, onPcm) {
  const source = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  proc.onaudioprocess = (event) => {
    const input = event.inputBuffer.getChannelData(0);
    onPcm(pcmFromAudioBuffer(input, ctx.sampleRate));
  };
  const mute = ctx.createGain();
  mute.gain.value = 0;
  source.connect(proc);
  proc.connect(mute);
  mute.connect(ctx.destination);
  processors.push(proc);
  return proc;
}

function stopCapture() {
  listening = false;
  processors.forEach((p) => {
    try { p.disconnect(); } catch { /* ignore */ }
  });
  processors = [];
  captureStreams.forEach((stream) => {
    stream.getTracks().forEach((t) => t.stop());
  });
  captureStreams = [];
  if (websocket) {
    try {
      if (websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({ type: 'CloseStream' }));
      }
      websocket.close();
    } catch { /* ignore */ }
    websocket = null;
  }
  if (audioContext) {
    audioContext.close().catch(() => {});
    audioContext = null;
  }
  btnListen.disabled = false;
  btnStop.disabled = true;
}

async function startListen() {
  const gate = canStartListen({
    hasToken: Boolean(localStorage.getItem(STORAGE.token)),
    isListening: listening,
  });
  if (!gate.ok) {
    showError(listenError, startDeniedMessage(gate.reason));
    return;
  }
  showError(listenError, '');
  let mic;
  let system;
  try {
    mic = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch {
    showError(listenError, startDeniedMessage('no_mic'));
    return;
  }
  try {
    system = await navigator.mediaDevices.getDisplayMedia({
      audio: true,
      video: true,
    });
    system.getVideoTracks().forEach((t) => t.stop());
  } catch {
    mic.getTracks().forEach((t) => t.stop());
    showError(listenError, startDeniedMessage('no_system_audio'));
    return;
  }
  if (!system.getAudioTracks().length) {
    mic.getTracks().forEach((t) => t.stop());
    system.getTracks().forEach((t) => t.stop());
    showError(listenError, startDeniedMessage('no_system_audio'));
    return;
  }

  listening = true;
  captureStreams = [mic, system];
  transcriptState = { finalTranscript: '', interimTranscript: '' };
  renderTranscript();
  btnListen.disabled = true;
  btnStop.disabled = false;
  statusEl.innerHTML = '<span class="live">Listening</span> to system audio (Them) and mic (You).';

  const wsUrl = applyChannelLabelsToLiveUrl(liveTranscriptionUrl(apiBase()), ['prospect', 'rep']);
  websocket = new WebSocket(wsUrl);
  websocket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type !== 'Results') return;
      const text = data.channel?.alternatives?.[0]?.transcript || '';
      const isFinal = data.is_final || data.speech_final;
      if (!text) return;
      transcriptState = applyTranscriptUpdate(transcriptState, {
        text,
        isFinal,
        audioChannel: data.audio_channel || null,
      });
      renderTranscript();
    } catch { /* ignore malformed frames */ }
  };
  websocket.onerror = () => {
    showError(listenError, 'Transcription connection failed. Check API base and network.');
  };

  audioContext = new AudioContext({ sampleRate: 16000 });
  const send = (channel) => (pcm) => {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.send(encodeChannelAudio(channel, pcm));
    }
  };
  hookPcm(audioContext, system, send('prospect'));
  hookPcm(audioContext, mic, send('rep'));
}

async function stopAndSend() {
  const transcript = `${transcriptState.finalTranscript} ${transcriptState.interimTranscript}`.trim();
  stopCapture();
  statusEl.textContent = 'Stopped.';
  if (!transcript) {
    showError(listenError, 'Nothing transcribed. Try again with the call unmuted.');
    return;
  }
  try {
    const token = localStorage.getItem(STORAGE.token);
    await request('/memos/upload-transcript', {
      method: 'POST',
      token,
      body: { transcript, source_type: 'meeting_transcript' },
    });
    statusEl.textContent = 'Sent to Vocify. Open the dashboard to review speakers and CRM fields.';
  } catch (err) {
    showError(listenError, err.message || 'Upload failed');
  }
}

document.getElementById('btn-login').addEventListener('click', async () => {
  showError(loginError, '');
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  const base = document.getElementById('api-base').value.trim() || PROD_API;
  localStorage.setItem(STORAGE.api, base.replace(/\/+$/, ''));
  try {
    const data = await request('/auth/login', { method: 'POST', body: { email, password } });
    localStorage.setItem(STORAGE.token, data.access_token);
    if (data.refresh_token) localStorage.setItem(STORAGE.refresh, data.refresh_token);
    localStorage.setItem(STORAGE.email, email);
    setLoggedIn(true);
  } catch (err) {
    showError(loginError, err.message || 'Login failed');
  }
});

document.getElementById('btn-logout').addEventListener('click', () => {
  stopCapture();
  localStorage.removeItem(STORAGE.token);
  localStorage.removeItem(STORAGE.refresh);
  setLoggedIn(false);
});

btnListen.addEventListener('click', () => {
  startListen().catch((err) => showError(listenError, err.message || 'Could not start'));
});
btnStop.addEventListener('click', () => {
  stopAndSend().catch((err) => showError(listenError, err.message || 'Could not stop'));
});

document.getElementById('api-base').value = localStorage.getItem(STORAGE.api) || PROD_API;
document.getElementById('email').value = localStorage.getItem(STORAGE.email) || '';
setLoggedIn(Boolean(localStorage.getItem(STORAGE.token)));
