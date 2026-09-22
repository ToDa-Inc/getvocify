import { applyChannelLabelsToLiveUrl, encodeChannelAudio, liveTranscriptionUrl } from '../lib/channels.js';
import { backendLabel } from '../lib/capture-labels.js';
import { pcmFromAudioBuffer } from '../lib/pcm.js';
import {
  applyTranscriptUpdate,
  buildListenSession,
  canStartListen,
  startDeniedMessage,
} from '../lib/listen-policy.js';
import { parseHubSpotRecordPage } from '../lib/hubspot-record-page.js';
import { reconcileTranscript, scrollFollow } from './shared/ui/transcript.js';
import './shared/ui/components/v-followup.js';
import { composeTarget } from './shared/ui/compose.js';
import {
  buildCopilotChecklistRequestBody,
  fetchCopilotChecklist,
} from '../lib/copilot-checklist.js';
import { memoMeetingChecklistView } from '../lib/memo-meeting-checklist.js';
import {
  buildCopilotSuggestRequestBody,
  markCopilotSuggestRequested,
  resetCopilotSuggestRequestDedupe,
  shouldRequestCopilotSuggest,
  streamCopilotSuggest,
} from '../lib/copilot-suggest.js';
import {
  beginMeetingListenAssist,
  resetLiveAssistOnStop,
  shouldApplyCopilotStreamPayload,
  shouldRequestLiveCopilotSuggest,
  turnOffLiveAssist,
} from '../lib/copilot-session.js';
import { PRODUCT_CONTEXT_STORAGE_KEY } from './shared/ui/copilot/product-context.js';
import {
  ensureSuggestProfileProductContext,
  resetSuggestProfileProductContextCache,
} from '../lib/suggest-profile-product-context.js';
import { liveAssistOverlayFromCopilotPayload } from '../lib/live-assist-overlay.js';
import { assistOverlayFields, dashboardMemosUrl, overlaySnippet } from '../lib/shell.js';
import { liveAssistKind } from './shared/ui/copilot/suggestion-state.js';
import { humanizeSaasError } from '../lib/saas.js';
import { listenPermissionGate, permissionAction, permissionCopy, PERMISSION } from '../lib/permissions.js';
import { pickMicConstraints } from '../lib/mic-devices.js';
import {
  buildApproveExtraction,
  canEditOrRemoveProposedField,
  omittedKeysFrom,
  proposedFieldKey,
} from '../lib/extraction-omit.js';
import {
  approvePayload,
  notesFromPreview,
  pickDeal,
  reviewFields,
  waitForReview,
} from '../lib/memo-review.js';
import {
  HOME_BRIEF_LOADING,
  homeBriefContactId,
  homeBriefDisplayLines,
  homeBriefRequestPath,
  shouldFetchHomeBrief,
} from '../lib/home-brief.js';
import {
  homeHoyCardsForDisplay,
  homeHoyListedItems,
  homeHoyRequestPath,
  shouldFetchHomeHoy,
  todayItemToCard,
} from '../lib/home-hoy.js';
import { renderToString } from './shared/ui/html.js';
import { applyDataI18n, strings, uiLangInput } from './shared/ui/i18n.js';
import {
  latestTaggedTurnBody,
  splitTaggedTranscript,
  stripSpeakerPrefix,
  turnRoleFromPart,
} from '../lib/transcript-turns.js';
import { renderTodayCard } from './shared/ui/today-card.js';

const PROD_API = 'https://api.getvocify.com/api/v1';
const STORAGE = {
  token: 'vocify_access',
  refresh: 'vocify_refresh',
  api: 'vocify_api_base',
  email: 'vocify_email',
};

function uiLang() {
  return uiLangInput(localStorage.getItem('vocify_lang'), navigator.language);
}

applyDataI18n(document, uiLang());

const loginPanel = document.getElementById('login-panel');
const permissionsPanel = document.getElementById('permissions-panel');
const listenPanel = document.getElementById('listen-panel');
const reviewPanel = document.getElementById('review-panel');
const loginError = document.getElementById('login-error');
const listenError = document.getElementById('listen-error');
const reviewError = document.getElementById('review-error');
const statusEl = document.getElementById('status');
const transcriptEl = document.getElementById('transcript');
const returnLiveBtn = document.getElementById('btn-return-live');
const btnListen = document.getElementById('btn-listen');
const btnStop = document.getElementById('btn-stop');
const liveDot = document.getElementById('live-dot');
const liveLabel = document.getElementById('live-label');
const timerEl = document.getElementById('timer');
const backendChip = document.getElementById('backend-chip');
const sessionChip = document.getElementById('session-chip');
const contactBriefEl = document.getElementById('contact-brief');
const homeHoyEl = document.getElementById('home-hoy');

function desktop() {
  return typeof window !== 'undefined' ? window.vocifyDesktop : undefined;
}

let listening = false;
let currentBackend = 'chromium';
let audioContext = null;
let websocket = null;
let captureStreams = [];
let processors = [];
let nativePcmUnsub = null;
let transcriptState = { finalTranscript: '', interimTranscript: '' };
let startedAt = 0;
let timerTick = null;
let permissionPoll = null;
let permissionState = { platform: desktop()?.platform, microphone: 'never_requested', systemAudio: 'never_requested' };
let reviewContext = null;
let copilotSuggestAbort = null;
let copilotChecklistAbort = null;
let reviewChecklistAbort = null;
let liveAssistChecklist = null;
/** Active listen session: callMode/contact only; never invent CRM ids here. */
let listenSession = null;
let liveAssistMeetingId = null;
/** HubSpot record page when known ({ objectType, recordId }), same shape as extension context. */
let hubspotRecordPage = hubspotRecordPageFromLocation();
let homeBriefCache = null;
let homeBriefFlight = null;
let homeHoyItems = [];
let homeHoyActed = [];
let homeHoyFlight = false;
let homeHoyStale = true;
let homeHoyUndoTick = null;

function hubspotRecordPageFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const objectType = params.get('objectType');
  const recordId = params.get('recordId');
  if (!objectType || recordId == null || recordId === '') return null;
  return { objectType, recordId };
}

function knownHubspotRecordPage() {
  if (hubspotRecordPage?.recordId != null) return hubspotRecordPage;
  try {
    const url = sessionStorage.getItem('vocify_hubspot_page_url');
    if (url) {
      const parsed = parseHubSpotRecordPage(url);
      if (parsed) return parsed;
    }
  } catch {
    /* ignore */
  }
  return null;
}
/** Live-assist slice forwarded to the overlay pill (copilot session fills this). */
export const liveAssistOverlay = { evidenceRefs: [] };

function resetLiveAssistOverlay() {
  const stop = resetLiveAssistOnStop();
  liveAssistMeetingId = stop.meetingId;
  Object.assign(liveAssistOverlay, stop.overlay);
  liveAssistChecklist = stop.checklist;
}

/** Copilot suggest/result payload — updates overlay live-assist slice. */
export function applyCopilotSuggestionPayload(payload, { callMode, channel } = {}) {
  const kind = liveAssistKind({ callMode, channel });
  Object.assign(liveAssistOverlay, liveAssistOverlayFromCopilotPayload(payload, { kind }));
  notifyShell();
}

function abortCopilotSuggest() {
  copilotSuggestAbort?.abort();
  copilotSuggestAbort = null;
}

async function requestCopilotChecklist() {
  const token = localStorage.getItem(STORAGE.token);
  const session = listenSession;
  if (!listening || !token || !session) return;
  const callMode = session.callMode ?? session.call_mode ?? 'call';
  if (callMode !== 'meeting') return;

  copilotChecklistAbort?.abort();
  const controller = new AbortController();
  copilotChecklistAbort = controller;
  try {
    const result = await fetchCopilotChecklist(fetch, {
      apiBase: apiBase(),
      token,
      body: buildCopilotChecklistRequestBody({ session }),
      signal: controller.signal,
    });
    if (controller.signal.aborted) return;
    if (result?.ok && result.data) {
      liveAssistChecklist = result.data;
      notifyShell();
    }
  } catch {
    /* keep previous checklist on failure */
  } finally {
    if (copilotChecklistAbort === controller) copilotChecklistAbort = null;
  }
}

async function requestCopilotSuggest(latestTurn) {
  const token = localStorage.getItem(STORAGE.token);
  if (
    !shouldRequestLiveCopilotSuggest({
      listening,
      assistEnabled: liveAssistOverlay.assistEnabled,
      hasToken: Boolean(token),
      latestTurn,
      shouldRequestTurn: shouldRequestCopilotSuggest,
    })
  ) {
    return;
  }
  abortCopilotSuggest();
  const controller = new AbortController();
  copilotSuggestAbort = controller;
  const transcriptWindow = `${transcriptState.finalTranscript} ${transcriptState.interimTranscript}`.trim();
  const session = listenSession ?? { callMode: 'call' };
  const overlayCallMode = session.callMode ?? session.call_mode ?? 'call';
  const productContext = localStorage.getItem(PRODUCT_CONTEXT_STORAGE_KEY) ?? '';
  const profileProductContext = await ensureSuggestProfileProductContext(productContext, {
    fetchImpl: fetch,
    apiBase: apiBase(),
    token,
  });
  try {
    const result = await streamCopilotSuggest(fetch, {
      apiBase: apiBase(),
      token,
      body: buildCopilotSuggestRequestBody({
        session,
        transcriptWindow,
        latestTurn,
        language: 'auto',
        productContext,
        profileProductContext,
      }),
      onPayload: (payload) => {
        if (!shouldApplyCopilotStreamPayload({ signalAborted: controller.signal.aborted })) return;
        applyCopilotSuggestionPayload(payload, { callMode: overlayCallMode });
      },
      signal: controller.signal,
    });
    if (result?.ok) markCopilotSuggestRequested(latestTurn);
  } catch {
    /* ignore aborted / network errors during live listen */
  } finally {
    if (copilotSuggestAbort === controller) copilotSuggestAbort = null;
  }
}

function apiBase() {
  return (localStorage.getItem(STORAGE.api) || document.getElementById('api-base').value || PROD_API)
    .trim()
    .replace(/\/+$/, '');
}

function showError(el, message) {
  el.hidden = !message;
  el.textContent = message || '';
}

function formatTimer(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const mins = String(Math.floor(total / 60)).padStart(2, '0');
  const secs = String(total % 60).padStart(2, '0');
  return `${mins}:${secs}`;
}

function stopHomeHoyUndoClock() {
  if (homeHoyUndoTick) clearInterval(homeHoyUndoTick);
  homeHoyUndoTick = null;
}

function startHomeHoyUndoClock() {
  stopHomeHoyUndoClock();
  homeHoyUndoTick = setInterval(() => paintHomeHoy(), 1000);
}

function paintHomeHoy() {
  if (!homeHoyEl || listenPanel.hidden) return;
  const token = localStorage.getItem(STORAGE.token);
  const nowMs = Date.now();
  const listed = homeHoyListedItems(homeHoyItems, homeHoyActed, nowMs);
  const cards = homeHoyCardsForDisplay({
    captureActive: listening,
    cards: listed.map(todayItemToCard),
  });

  homeHoyEl.replaceChildren();
  if (!token || !cards.length) {
    homeHoyEl.hidden = true;
    stopHomeHoyUndoClock();
  } else {
    const t = strings(uiLang());
    for (const card of cards) {
      const wrap = document.createElement('div');
      wrap.innerHTML = renderToString(
        renderTodayCard(card, { now: nowMs, dismiss: t.dismiss, undo: t.undo }),
      );
      homeHoyEl.append(wrap.firstElementChild ?? wrap);
    }
    homeHoyEl.hidden = false;
    const undoOpen = cards.some(
      (card) => card.undoDeadline != null && Date.parse(card.undoDeadline) >= nowMs,
    );
    if (undoOpen) startHomeHoyUndoClock();
    else stopHomeHoyUndoClock();
  }

  if (
    shouldFetchHomeHoy({
      token,
      captureActive: listening,
      inFlight: homeHoyFlight,
      stale: homeHoyStale,
    })
  ) {
    homeHoyFlight = true;
    request(homeHoyRequestPath(), { token })
      .then((body) => {
        homeHoyItems = Array.isArray(body?.items) ? body.items : [];
        homeHoyFlight = false;
        homeHoyStale = false;
        paintHomeHoy();
      })
      .catch(() => {
        homeHoyFlight = false;
      });
  }
}

async function dismissHomeHoyCard(cardEl) {
  const id = cardEl?.dataset?.id;
  if (!id) return;
  const item = homeHoyListedItems(homeHoyItems, homeHoyActed, Date.now()).find((row) => row.id === id);
  if (!item?.id || item.version == null) return;
  const token = localStorage.getItem(STORAGE.token);
  if (!token) return;
  try {
    const result = await request(`/today/${item.id}/resolve`, {
      method: 'POST',
      token,
      body: {
        action: 'dismiss',
        request_id: crypto.randomUUID(),
        expected_version: item.version,
      },
    });
    homeHoyActed = [
      ...homeHoyActed.filter((row) => row.id !== item.id),
      {
        ...item,
        status: result.status,
        version: result.version,
        undo_deadline: result.undo_deadline,
      },
    ];
    paintHomeHoy();
  } catch {
    /* failed dismiss leaves the card */
  }
}

async function undoHomeHoyCard(cardEl) {
  const id = cardEl?.dataset?.id;
  if (!id) return;
  const item = homeHoyListedItems(homeHoyItems, homeHoyActed, Date.now()).find((row) => row.id === id);
  if (!item?.id || item.version == null) return;
  const token = localStorage.getItem(STORAGE.token);
  if (!token) return;
  try {
    await request(`/today/${item.id}`, {
      method: 'PATCH',
      token,
      body: {
        request_id: crypto.randomUUID(),
        expected_version: item.version,
      },
    });
    homeHoyActed = homeHoyActed.filter((row) => row.id !== item.id);
    homeHoyStale = true;
    paintHomeHoy();
  } catch {
    /* keep card as-is */
  }
}

function paintHomeBrief() {
  if (!contactBriefEl || listenPanel.hidden) return;
  hubspotRecordPage = knownHubspotRecordPage() ?? hubspotRecordPage;
  const recordPage = hubspotRecordPage;
  const lines = homeBriefDisplayLines({
    recordPage,
    captureActive: listening,
    cache: homeBriefCache,
    flightContactId: homeBriefFlight,
  });
  contactBriefEl.replaceChildren();
  for (const line of lines) {
    const row = document.createElement('p');
    row.className = line === HOME_BRIEF_LOADING ? 'v-followup__hint' : 'v-followup__body';
    row.textContent = line;
    contactBriefEl.append(row);
  }
  contactBriefEl.hidden = lines.length === 0;

  if (
    !shouldFetchHomeBrief({
      recordPage,
      captureActive: listening,
      cache: homeBriefCache,
      flightContactId: homeBriefFlight,
    })
  ) {
    return;
  }
  const contactId = homeBriefContactId(recordPage);
  const token = localStorage.getItem(STORAGE.token);
  if (!contactId || !token) return;
  homeBriefFlight = contactId;
  request(homeBriefRequestPath(contactId), { token })
    .then((body) => {
      if (homeBriefFlight !== contactId) return;
      homeBriefCache = { contactId, brief: body };
      homeBriefFlight = null;
      paintHomeBrief();
    })
    .catch(() => {
      if (homeBriefFlight !== contactId) return;
      homeBriefCache = { contactId, brief: { text: 'No se pudo cargar todo.', lines: [] } };
      homeBriefFlight = null;
      paintHomeBrief();
    });
}

function notifyShell() {
  const email = localStorage.getItem(STORAGE.email) || '';
  if (sessionChip) {
    sessionChip.hidden = !email;
    sessionChip.textContent = email;
  }
  desktop()?.shell?.setState({
    listening,
    loggedIn: Boolean(localStorage.getItem(STORAGE.token)),
    lastLine: overlaySnippet(transcriptState, uiLang()),
    backend: currentBackend,
    email,
    apiBase: apiBase(),
    meetingId: liveAssistMeetingId,
    ...assistOverlayFields(liveAssistOverlay),
    checklist: liveAssistChecklist,
  });
}

function setLiveUi(on) {
  const t = strings(uiLang());
  liveDot.classList.toggle('live', on);
  liveDot.classList.toggle('idle', !on);
  liveLabel.textContent = on ? t.listenLiveStatus : t.desktopIdle;
  if (on) {
    startedAt = Date.now();
    timerEl.textContent = '00:00';
    clearInterval(timerTick);
    timerTick = setInterval(() => {
      timerEl.textContent = formatTimer(Date.now() - startedAt);
    }, 250);
  } else {
    clearInterval(timerTick);
    timerTick = null;
  }
}

function showScreen(name) {
  loginPanel.hidden = name !== 'login';
  permissionsPanel.hidden = name !== 'permissions';
  listenPanel.hidden = name !== 'listen';
  reviewPanel.hidden = name !== 'review';
  desktop()?.shell?.resize(name === 'review' ? 'review' : 'compact');
  if (name === 'listen') {
    paintHomeBrief();
    paintHomeHoy();
  } else {
    if (contactBriefEl) contactBriefEl.hidden = true;
    if (homeHoyEl) homeHoyEl.hidden = true;
    stopHomeHoyUndoClock();
  }
  notifyShell();
}

function permissionGate() {
  return listenPermissionGate({
    platform: permissionState.platform || desktop()?.platform,
    microphone: permissionState.microphone,
    systemAudio: permissionState.systemAudio,
  });
}

function paintPermissionRow(row, type, status) {
  const copy = permissionCopy(type);
  const on = status === 'authorized';
  row.classList.toggle('is-on', on);
  row.querySelector('[data-title]').textContent = on ? copy.enabledLabel : copy.enableLabel;
  row.querySelector('[data-body]').textContent = on ? copy.enabledBody : copy.enableBody;
  const btn = row.querySelector('[data-action]');
  btn.hidden = on;
  btn.textContent = permissionAction(status) === 'open_settings' ? 'Open Settings' : 'Enable';
}

async function refreshPermissions() {
  const api = desktop()?.permissions;
  if (!api?.status) {
    permissionState = { platform: desktop()?.platform, microphone: 'authorized', systemAudio: 'authorized' };
    return permissionState;
  }
  permissionState = await api.status();
  paintPermissionRow(document.getElementById('perm-mic'), PERMISSION.microphone, permissionState.microphone);
  paintPermissionRow(document.getElementById('perm-audio'), PERMISSION.systemAudio, permissionState.systemAudio);
  document.getElementById('btn-permissions-continue').disabled = !permissionGate().ok;
  return permissionState;
}

function startPermissionPoll() {
  stopPermissionPoll();
  permissionPoll = setInterval(() => {
    refreshPermissions().catch(() => {});
  }, 1000);
}

function stopPermissionPoll() {
  if (permissionPoll) clearInterval(permissionPoll);
  permissionPoll = null;
}

async function enterApp() {
  await refreshPermissions();
  if (!permissionGate().ok) {
    showScreen('permissions');
    startPermissionPoll();
    return;
  }
  stopPermissionPoll();
  showScreen('listen');
}

async function handlePermissionClick(type) {
  const api = desktop()?.permissions;
  if (!api) return;
  const status = type === PERMISSION.microphone ? permissionState.microphone : permissionState.systemAudio;
  if (permissionAction(status) === 'open_settings') await api.open(type);
  else await api.request(type);
  await refreshPermissions();
}

async function request(path, { method = 'GET', body, token } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const proxy = desktop()?.saas?.request;
  try {
    if (proxy) {
      const result = await proxy({ base: apiBase(), path, method, headers, body });
      if (!result.ok) {
        const detail = typeof result.data?.detail === 'string' ? result.data.detail : result.error;
        throw new Error(humanizeSaasError(null, { status: result.status, detail }));
      }
      return result.data;
    }
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
  } catch (err) {
    throw new Error(humanizeSaasError(err, { detail: err?.message }));
  }
}

let transcriptView = { revision: 0, turns: [], interim: null };
let stickToLive = true;

function renderTranscript() {
  const legacy = `${transcriptState.finalTranscript} ${transcriptState.interimTranscript}`.trim();
  const next = {
    revision: transcriptView.revision + 1,
    turns: legacy
      ? [{ id: 'live', text: legacy }]
      : [],
    interim: null,
  };
  transcriptView = reconcileTranscript(transcriptView, next) ?? next;
  const follow = stickToLive;
  const text = transcriptView.turns.map((turn) => turn.text).join(' ').trim();
  const parts = text ? splitTaggedTranscript(text) : [];
  const t = strings(uiLang());
  if (!parts.length) {
    transcriptEl.querySelectorAll('.turn').forEach((node) => node.remove());
    if (!transcriptEl.querySelector('.empty')) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = 'Escuchando. La transcripción aparecerá aquí.';
      transcriptEl.append(empty);
    }
  } else {
    transcriptEl.querySelector('.empty')?.remove();
    const rows = [...transcriptEl.querySelectorAll('.turn')];
    parts.forEach((part, index) => {
      const role = turnRoleFromPart(part);
      let row = rows[index];
      if (!row) {
        row = document.createElement('div');
        row.className = 'turn v-transcript-turn';
        row.append(document.createElement('span'), document.createElement('div'));
        transcriptEl.append(row);
      }
      const roleClass = role === 'rep' ? 'you' : role === 'prospect' ? 'them' : '';
      row.className = `turn v-transcript-turn${roleClass ? ` ${roleClass}` : ''}`;
      const speaker = row.children[0];
      speaker.className = 'speaker';
      speaker.textContent =
        role === 'rep' ? t.speakerYou : role === 'prospect' ? t.speakerThem : '';
      const bubble = row.children[1];
      bubble.className = 'bubble';
      const body = stripSpeakerPrefix(part);
      if (bubble.textContent !== body) bubble.textContent = body;
    });
    rows.slice(parts.length).forEach((node) => node.remove());
  }
  if (returnLiveBtn) {
    returnLiveBtn.hidden = follow || !parts.length;
    returnLiveBtn.textContent = 'Volver al directo';
  }
  if (follow) transcriptEl.scrollTop = transcriptEl.scrollHeight;
  notifyShell();
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
  abortCopilotSuggest();
  copilotChecklistAbort?.abort();
  copilotChecklistAbort = null;
  resetCopilotSuggestRequestDedupe();
  resetSuggestProfileProductContextCache();
  resetLiveAssistOverlay();
  listenSession = null;
  listening = false;
  processors.forEach((p) => {
    try { p.disconnect(); } catch { /* ignore */ }
  });
  processors = [];
  captureStreams.forEach((stream) => {
    stream.getTracks().forEach((t) => t.stop());
  });
  captureStreams = [];
  if (nativePcmUnsub) {
    try { nativePcmUnsub(); } catch { /* ignore */ }
    nativePcmUnsub = null;
  }
  const native = desktop()?.systemAudio;
  if (native?.stop) {
    Promise.resolve(native.stop()).catch(() => {});
  }
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
  setLiveUi(false);
  desktop()?.shell?.hideOverlay();
  paintHomeBrief();
  homeHoyStale = true;
  paintHomeHoy();
  notifyShell();
}

async function startListen() {
  await refreshPermissions();
  const gate = canStartListen({
    hasToken: Boolean(localStorage.getItem(STORAGE.token)),
    isListening: listening,
    permissionGate: permissionGate(),
  });
  if (!gate.ok) {
    if (gate.reason === 'no_mic' || gate.reason === 'no_system_audio') {
      showScreen('permissions');
      startPermissionPoll();
    }
    showError(
      listenError,
      startDeniedMessage(gate.reason, { platform: desktop()?.platform, lang: uiLang() }),
    );
    return;
  }
  showError(listenError, '');
  const platform = desktop()?.platform;
  let mic;
  let system;
  let nativeBackend = null;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    mic = await navigator.mediaDevices.getUserMedia(pickMicConstraints(devices));
  } catch {
    showError(listenError, startDeniedMessage('no_mic', { platform, lang: uiLang() }));
    return;
  }
  const native = desktop()?.systemAudio;
  if (native?.start) {
    try {
      const started = await native.start();
      if (started?.ok) nativeBackend = started.backend;
    } catch {
      nativeBackend = null;
    }
  }
  if (!nativeBackend) {
    try {
      system = await navigator.mediaDevices.getDisplayMedia({
        audio: true,
        video: true,
      });
      system.getVideoTracks().forEach((t) => t.stop());
    } catch {
      mic.getTracks().forEach((t) => t.stop());
      showError(listenError, startDeniedMessage('no_system_audio', { platform, lang: uiLang() }));
      return;
    }
    if (!system.getAudioTracks().length) {
      mic.getTracks().forEach((t) => t.stop());
      system.getTracks().forEach((t) => t.stop());
      showError(listenError, startDeniedMessage('no_system_audio', { platform, lang: uiLang() }));
      return;
    }
  }

  listening = true;
  currentBackend = nativeBackend || 'chromium';
  captureStreams = system ? [mic, system] : [mic];
  hubspotRecordPage = knownHubspotRecordPage() ?? hubspotRecordPage;
  listenSession = buildListenSession({
    callMode: 'meeting',
    crmPageContext: hubspotRecordPage,
  });
  const listenAssist = beginMeetingListenAssist({ createMeetingId: () => crypto.randomUUID() });
  liveAssistMeetingId = listenAssist.meetingId;
  Object.assign(liveAssistOverlay, listenAssist.overlay);
  liveAssistChecklist = listenAssist.checklist;
  transcriptState = { finalTranscript: '', interimTranscript: '' };
  if (listenAssist.resetSuggestDedupe) resetCopilotSuggestRequestDedupe();
  resetSuggestProfileProductContextCache();
  renderTranscript();
  btnListen.disabled = true;
  btnStop.disabled = false;
  setLiveUi(true);
  backendChip.textContent = backendLabel(currentBackend);
  statusEl.textContent = strings(uiLang()).desktopHearing;
  desktop()?.shell?.showOverlay();
  paintHomeBrief();
  paintHomeHoy();
  notifyShell();

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
        lang: uiLang(),
      });
      if (isFinal) {
        const latestTurn = latestTaggedTurnBody(transcriptState.finalTranscript);
        void requestCopilotSuggest(latestTurn);
        void requestCopilotChecklist();
      }
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
  hookPcm(audioContext, mic, send('rep'));
  if (system) {
    hookPcm(audioContext, system, send('prospect'));
  } else if (native?.onPcm) {
    nativePcmUnsub = native.onPcm((pcm) => send('prospect')(pcm));
  }
}

function reviewChecklistCopy() {
  const lang = uiLang();
  const t = strings(lang);
  const progressTemplate = lang === 'es' ? '{met} de {applicable}' : '{met} of {applicable}';
  return { progressTemplate, doneLabel: t.checklistDone };
}

function paintReviewChecklist(checklist) {
  const el = document.getElementById('review-checklist');
  if (!el) return;
  const view = memoMeetingChecklistView(checklist, reviewChecklistCopy());
  el.replaceChildren();
  if (!view) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  const summary = document.createElement('p');
  summary.className = 'caps overlay-checklist-summary';
  summary.textContent = view.progress;
  el.appendChild(summary);
  for (const step of view.steps) {
    const row = document.createElement('p');
    row.className = 'line overlay-checklist-step';
    if (step.kind === 'met') {
      const labelSpan = document.createElement('span');
      labelSpan.textContent = step.label;
      const doneSpan = document.createElement('span');
      doneSpan.className = 'muted';
      doneSpan.textContent = step.doneLabel;
      row.append(labelSpan, document.createTextNode(' '), doneSpan);
    } else {
      row.textContent = step.label;
    }
    el.appendChild(row);
  }
}

async function loadReviewChecklist(memoId, token) {
  reviewChecklistAbort?.abort();
  const controller = new AbortController();
  reviewChecklistAbort = controller;
  let checklist = null;
  try {
    const result = await fetchCopilotChecklist(fetch, {
      apiBase: apiBase(),
      token,
      body: buildCopilotChecklistRequestBody({ session: { capture_id: memoId } }),
      signal: controller.signal,
    });
    if (controller.signal.aborted || reviewContext?.memoId !== memoId) return;
    checklist = result.ok ? result.data : null;
  } catch {
    if (controller.signal.aborted || reviewContext?.memoId !== memoId) return;
    checklist = null;
  } finally {
    if (reviewChecklistAbort === controller) reviewChecklistAbort = null;
  }
  if (reviewContext?.memoId !== memoId) return;
  reviewContext.meetingChecklist = checklist;
  paintReviewChecklist(checklist);
}

function renderReview() {
  const ctx = reviewContext;
  if (!ctx) return;
  const summaryEl = document.getElementById('review-summary');
  const nextEl = document.getElementById('review-next');
  if (summaryEl.value) ctx.summary = summaryEl.value;
  if (nextEl.value) ctx.nextSteps = nextEl.value.split('\n').map((line) => line.trim()).filter(Boolean);
  const notes = notesFromPreview(ctx.preview, ctx.memo?.extraction);
  summaryEl.value = ctx.summary ?? notes.summary;
  nextEl.value = (ctx.nextSteps || notes.nextSteps).join('\n');
  const dealEl = document.getElementById('review-deal');
  const dealsEl = document.getElementById('review-deals');
  if (ctx.deal.needsDecision) {
    dealEl.textContent = 'Pick the HubSpot deal for this call.';
    dealsEl.hidden = false;
    dealsEl.innerHTML = '';
    for (const match of ctx.deal.matches || []) {
      const label = document.createElement('label');
      label.className = 'deal-option';
      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'review-deal';
      radio.value = match.deal_id;
      radio.checked = ctx.dealId === match.deal_id;
      radio.addEventListener('change', () => {
        ctx.dealId = match.deal_id;
        ctx.isNewDeal = false;
      });
      const text = document.createElement('span');
      text.textContent = `${match.deal_name || match.deal_id} (${Math.round((match.match_confidence || 0) * 100)}%)`;
      label.append(text, radio);
      dealsEl.appendChild(label);
    }
    const create = document.createElement('label');
    create.className = 'deal-option';
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'review-deal';
    radio.value = '';
    radio.addEventListener('change', () => {
      ctx.dealId = null;
      ctx.isNewDeal = true;
    });
    const text = document.createElement('span');
    text.textContent = 'Create a new deal';
    create.append(text, radio);
    dealsEl.appendChild(create);
  } else {
    dealsEl.hidden = true;
    dealEl.textContent = ctx.deal.selected
      ? `Matched: ${ctx.deal.selected.deal_name || ctx.deal.selected.deal_id}`
      : 'No confident deal match — Approve can still update the contact.';
  }

  const fieldsEl = document.getElementById('review-fields');
  fieldsEl.innerHTML = '';
  for (const row of ctx.updates) {
    const wrap = document.createElement('div');
    wrap.className = 'field-row';
    const block = document.createElement('label');
    block.textContent = row.field_label || row.field_name;
    const input = document.createElement('input');
    input.value = row.new_value ?? '';
    input.addEventListener('input', () => {
      row.new_value = input.value;
    });
    block.appendChild(input);
    wrap.appendChild(block);
    if (canEditOrRemoveProposedField(row)) {
      const omit = document.createElement('button');
      omit.type = 'button';
      omit.className = 'ghost omit';
      omit.textContent = 'Omit';
      omit.addEventListener('click', () => {
        const key = proposedFieldKey(row);
        if (key) ctx.omittedKeys.push(key);
        ctx.updates = ctx.updates.filter((item) => item !== row);
        renderReview();
      });
      wrap.appendChild(omit);
    }
    fieldsEl.appendChild(wrap);
  }
  if (!ctx.updates.length) {
    fieldsEl.innerHTML = '<p class="muted">No field updates extracted.</p>';
  }
  paintReviewChecklist(ctx.meetingChecklist);
}

const followupEl = document.getElementById('review-followup');
let followupTimer = null;

async function loadFollowup(memoId, token, attempt = 0) {
  clearTimeout(followupTimer);
  if (reviewContext?.memoId !== memoId) return;
  let view;
  try {
    view = await request(`/memos/${memoId}/followup`, { token });
  } catch {
    followupEl.hidden = true;
    return;
  }
  if (reviewContext?.memoId !== memoId) return;
  followupEl.hidden = view.status === 'unavailable';
  followupEl.data = view;
  if (view.status === 'generating' && attempt < 25) {
    followupTimer = setTimeout(() => loadFollowup(memoId, token, attempt + 1), 1500);
  }
}

followupEl.addEventListener('v-action', async (event) => {
  const { action, value, element } = event.detail;
  const memoId = reviewContext?.memoId;
  const view = element.data;
  if (!memoId || !view) return;
  const token = localStorage.getItem(STORAGE.token);
  const { subject, body } = element.value;
  const record = (payload) => request(`/memos/${memoId}/followup`, { method: 'POST', token, body: payload });
  try {
    if (action === 'copy') {
      await navigator.clipboard.writeText(body);
      await record({ action: 'copied', channel: 'email', subject, body });
      return;
    }
    const channel = value === 'whatsapp' ? 'whatsapp' : 'email';
    const target = composeTarget({ channel, to: view.to, phone: view.phone, subject, body });
    const url = target.ok ? target.url : target.fallback;
    if (!url) return;
    if (!target.ok) await navigator.clipboard.writeText(body);
    const opened = await window.vocifyDesktop.shell.openExternal(url);
    if (!opened?.ok) return;
    element.data = await record({ action: 'sent', channel, subject, body });
  } catch (err) {
    showError(reviewError, err.message || 'Follow-up failed');
  }
});

async function openReview(memoId) {
  showScreen('review');
  document.getElementById('review-status').textContent = 'Extracting CRM fields…';
  showError(reviewError, '');
  const token = localStorage.getItem(STORAGE.token);
  const waited = await waitForReview(() => request(`/memos/${memoId}`, { token }));
  if (!waited.ok) {
    document.getElementById('review-status').textContent = '';
    showError(reviewError, waited.error || 'Extraction failed');
    return;
  }
  const memo = waited.memo;
  let preview = {};
  try {
    preview = await request(`/memos/${memoId}/preview`, { token });
  } catch (err) {
    showError(reviewError, err.message || 'Preview failed');
  }
  const deal = pickDeal(preview.matched_deals || preview.matches || []);
  const notes = notesFromPreview(preview, memo.extraction);
  reviewContext = {
    memoId,
    memo,
    preview,
    deal,
    dealId: deal.dealId,
    isNewDeal: false,
    originalUpdates: reviewFields(preview),
    updates: reviewFields(preview).map((row) => ({ ...row })),
    omittedKeys: [],
    summary: notes.summary,
    nextSteps: notes.nextSteps,
    meetingChecklist: null,
  };
  document.getElementById('review-status').textContent = 'Review notes and fields, then approve.';
  paintReviewChecklist(null);
  loadFollowup(memoId, token);
  renderReview();
  void loadReviewChecklist(memoId, token);
}

async function stopAndSend() {
  const transcript = `${transcriptState.finalTranscript} ${transcriptState.interimTranscript}`.trim();
  stopCapture();
  statusEl.textContent = strings(uiLang()).desktopStopped;
  if (!transcript) {
    showError(listenError, 'Nothing transcribed. Try again with the call unmuted.');
    return;
  }
  try {
    const token = localStorage.getItem(STORAGE.token);
    const uploaded = await request('/memos/upload-and-extract', {
      method: 'POST',
      token,
      body: { transcript, source_type: 'meeting_transcript' },
    });
    statusEl.textContent = 'Sent to Vocify.';
    await openReview(uploaded.id);
  } catch (err) {
    showError(listenError, err.message || 'Upload failed');
  }
}

async function approveReview() {
  if (!reviewContext) return;
  showError(reviewError, '');
  const summary = document.getElementById('review-summary').value;
  const nextSteps = document.getElementById('review-next').value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const omitted = [
    ...reviewContext.omittedKeys,
    ...omittedKeysFrom(reviewContext.originalUpdates, reviewContext.updates),
  ];
  const extraction = buildApproveExtraction({
    memoExtraction: reviewContext.memo?.extraction || {},
    updates: reviewContext.updates,
    omittedKeys: omitted,
    summary,
    nextSteps,
  });
  const token = localStorage.getItem(STORAGE.token);
  const contact = reviewContext.preview?.selected_contact;
  try {
    document.getElementById('btn-approve').disabled = true;
    await request(`/memos/${reviewContext.memoId}/approve`, {
      method: 'POST',
      token,
      body: approvePayload({
        dealId: reviewContext.dealId,
        isNewDeal: reviewContext.isNewDeal,
        extraction,
        contactId: contact?.contact_id,
        companyId: contact?.company_id,
        skipDeal: Boolean(reviewContext.preview?.skip_deal) && !reviewContext.dealId && !reviewContext.isNewDeal,
      }),
    });
    document.getElementById('review-status').textContent = 'CRM updated.';
  } catch (err) {
    showError(reviewError, err.message || 'Approve failed');
  } finally {
    document.getElementById('btn-approve').disabled = false;
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
    await enterApp();
  } catch (err) {
    showError(loginError, err.message || 'Login failed');
  }
});

homeHoyEl?.addEventListener('click', (event) => {
  const action = event.target.closest('[data-action]');
  if (!action || !homeHoyEl.contains(action)) return;
  const cardEl = action.closest('.v-today-card');
  if (!cardEl) return;
  if (action.dataset.action === 'dismiss') {
    dismissHomeHoyCard(cardEl).catch(() => {});
  } else if (action.dataset.action === 'undo') {
    undoHomeHoyCard(cardEl).catch(() => {});
  }
});

document.getElementById('btn-logout').addEventListener('click', () => {
  stopCapture();
  stopPermissionPoll();
  stopHomeHoyUndoClock();
  homeHoyItems = [];
  homeHoyActed = [];
  homeHoyStale = true;
  localStorage.removeItem(STORAGE.token);
  localStorage.removeItem(STORAGE.refresh);
  showScreen('login');
});

document.getElementById('btn-dashboard').addEventListener('click', () => {
  desktop()?.shell?.openExternal(dashboardMemosUrl(apiBase()));
});

document.getElementById('perm-mic').querySelector('[data-action]').addEventListener('click', () => {
  handlePermissionClick(PERMISSION.microphone).catch(() => {});
});
document.getElementById('perm-audio').querySelector('[data-action]').addEventListener('click', () => {
  handlePermissionClick(PERMISSION.systemAudio).catch(() => {});
});
document.getElementById('btn-permissions-continue').addEventListener('click', () => {
  if (permissionGate().ok) {
    stopPermissionPoll();
    showScreen('listen');
  }
});

transcriptEl.addEventListener('scroll', () => {
  stickToLive = scrollFollow({
    scrollTop: transcriptEl.scrollTop,
    scrollHeight: transcriptEl.scrollHeight,
    clientHeight: transcriptEl.clientHeight,
  }).follow;
  if (returnLiveBtn) returnLiveBtn.hidden = stickToLive || !transcriptEl.querySelector('.turn');
});
returnLiveBtn?.addEventListener('click', () => {
  stickToLive = true;
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
  returnLiveBtn.hidden = true;
});

btnListen.addEventListener('click', () => {
  startListen().catch((err) =>
    showError(listenError, err.message || strings(uiLang()).listenCouldNotStart),
  );
});
btnStop.addEventListener('click', () => {
  stopAndSend().catch((err) => showError(listenError, err.message || 'Could not stop'));
});
document.getElementById('btn-approve').addEventListener('click', () => {
  approveReview().catch((err) => showError(reviewError, err.message || 'Approve failed'));
});
document.getElementById('btn-review-back').addEventListener('click', () => {
  showScreen('listen');
});

desktop()?.shell?.onCommand((command) => {
  if (command === 'listen') {
    startListen().catch((err) =>
      showError(listenError, err.message || strings(uiLang()).listenCouldNotStart),
    );
  }
  if (command === 'stop') stopAndSend().catch((err) => showError(listenError, err.message || 'Could not stop'));
  if (command === 'assist-on') {
    liveAssistOverlay.assistEnabled = true;
    notifyShell();
    const latestTurn = latestTaggedTurnBody(transcriptState.finalTranscript);
    if (latestTurn) void requestCopilotSuggest(latestTurn);
  }
  if (command === 'assist-off') {
    const off = turnOffLiveAssist(liveAssistOverlay);
    if (off.shouldAbortSuggest) abortCopilotSuggest();
    notifyShell();
  }
});

document.getElementById('api-base').value = localStorage.getItem(STORAGE.api) || PROD_API;
document.getElementById('email').value = localStorage.getItem(STORAGE.email) || '';
if (localStorage.getItem(STORAGE.token)) enterApp();
else showScreen('login');
