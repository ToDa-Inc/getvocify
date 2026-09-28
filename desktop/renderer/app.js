import { desktopCopy } from '../lib/desktop-copy.js';
import { applyChannelLabelsToLiveUrl, encodeChannelAudio, liveTranscriptionUrl } from '../lib/channels.js';
import { pcmFromAudioBuffer } from '../lib/pcm.js';
import {
  applyTranscriptUpdate,
  buildListenSession,
  canStartListen,
  startDeniedMessage,
} from '../lib/listen-policy.js';
import { parseHubSpotRecordPage } from '../lib/hubspot-record-page.js';
import { scrollFollow } from './shared/ui/transcript.js';
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
import {
  applyPermissionSnapshot,
  listenPermissionGate,
  PERMISSION,
  permissionAction,
} from '../lib/permissions.js';
import { pickMicConstraints } from '../lib/mic-devices.js';
import { noteRows, notesRequestPath } from '../lib/notes-list.js';
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
import { applyDataI18n, strings, uiLangInput, resolveUiLang } from './shared/ui/i18n.js';
import { applyChunk, emptyNote, latestFinal, noteUploadText } from '../lib/live-note.js';
import { renderTodayCard } from './shared/ui/today-card.js';
import { isSessionError, startScreen } from '../lib/session.js';
import { completeDesktopCapture, reserveDesktopCapture } from '../lib/capture-upload.js';

const PROD_API = 'https://api.getvocify.com/api/v1';
const STORAGE = {
  token: 'vocify_access',
  refresh: 'vocify_refresh',
  api: 'vocify_api_base',
  email: 'vocify_email',
  macPermissionsReady: 'vocify_mac_permissions_ready',
};

function uiLang() {
  return resolveUiLang(uiLangInput(localStorage.getItem('vocify_lang'), navigator.language));
}

applyDataI18n(document, uiLang());
document.documentElement.lang = uiLang();
for (const el of document.querySelectorAll('[data-desktop-i18n]')) el.textContent = desktopCopy(uiLang())[el.dataset.desktopI18n] || '';
const copy = () => desktopCopy(uiLang());

const loginPanel = document.getElementById('login-panel');
const permissionsPanel = document.getElementById('permissions-panel');
const listenPanel = document.getElementById('listen-panel');
const reviewPanel = document.getElementById('review-panel');
const listenPermissionsEl = document.getElementById('listen-permissions');
const loginError = document.getElementById('login-error');
const listenError = document.getElementById('listen-error');
const reviewError = document.getElementById('review-error');
const transcriptEl = document.getElementById('transcript');
const returnLiveBtn = document.getElementById('btn-return-live');
const btnRecord = document.getElementById('btn-record');
const recordHint = document.getElementById('record-hint');
const idleBlockEl = document.getElementById('idle-block');
const liveChipEl = document.getElementById('live-chip');
const assistToggleEl = document.getElementById('assist-toggle');
const assistInputEl = document.getElementById('assist-input');
const btnOpenSettings = document.getElementById('btn-open-settings');
const timerEl = document.getElementById('timer');
const accountMenu = document.getElementById('account-menu');
const sessionChip = document.getElementById('session-chip');
const contactBriefEl = document.getElementById('contact-brief');
const homeHoyEl = document.getElementById('home-hoy');
const notesRailEl = document.getElementById('notes-rail');
const notesListEl = document.getElementById('notes-list');
const reviewNoteEl = document.getElementById('review-note');
const btnReviewRetry = document.getElementById('btn-review-retry');
const btnReviewDashboard = document.getElementById('btn-review-dashboard');

function desktop() {
  return typeof window !== 'undefined' ? window.vocifyDesktop : undefined;
}

let listening = false;
let currentBackend = 'chromium';
let audioContext = null;
let websocket = null;
let wsIntentionalClose = false;
let wsReconnectAttempts = 0;
let wsReconnectTimer = null;
let transcriptionOffline = false;
let clientCaptureId = null;
let captureStreams = [];
let processors = [];
let nativePcmUnsub = null;
let nativeLostUnsub = null;
let transcriptState = { finalTranscript: '', interimTranscript: '' };
let liveNote = emptyNote();
let startedAt = 0;
let timerTick = null;
let permissionState = { platform: desktop()?.platform, microphone: 'never_requested', systemAudio: 'never_requested' };
let permissionPoll = null;
let notesCache = [];
let reviewContext = null;
let reviewLoadGeneration = 0;
/** Live note frozen when entering review from stop; cleared when opening another memo from the rail. */
let reviewNoteSnapshot = null;
/** Transcript text for retry after upload/extraction failure while on the review screen. */
let pendingReviewTranscript = null;
/** Memo on screen when review failed during load (rail or post-upload extract). */
let reviewRetryMemoId = null;
let reviewRetryReadOnly = false;
/** Server capture id when complete failed after stop (same memo, no duplicate upload). */
let reviewRetryCaptureId = null;
let reviewRetryDurationSec = null;
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
let homeHoyError = false;
let homeHoyCoverage = null;
let localPendingCaptures = [];
/** Server memo id from POST /captures during an active listen session. */
let serverCaptureMemoId = null;

function pendingCaptureSendLabel() {
  return uiLang() === 'en' ? 'Send' : 'Enviar';
}

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
  return (localStorage.getItem(STORAGE.api) || PROD_API).trim().replace(/\/+$/, '');
}

function showError(el, message) {
  el.hidden = !message;
  el.textContent = message || '';
  if (el === listenError && btnOpenSettings) btnOpenSettings.hidden = true;
}

function permissionTypeForDenyReason(reason) {
  if (reason === 'no_mic') return PERMISSION.microphone;
  if (reason === 'no_system_audio') return PERMISSION.systemAudio;
  return null;
}

function showListenDenied(reason, platform) {
  const type = permissionTypeForDenyReason(reason);
  if (type && needsMacPermissions()) {
    showError(listenError, '');
    if (btnOpenSettings) btnOpenSettings.hidden = true;
    void refreshPermissions().then(() => {
      paintListenPermissionGate();
      syncPermissionPoll();
    });
    return;
  }
  showError(listenError, startDeniedMessage(reason, { platform, lang: uiLang() }));
}

function showMeetingAudioLost() {
  const t = strings(uiLang());
  if (listenError) {
    listenError.hidden = false;
    listenError.textContent = t.desktopNoMeetingAudio;
  }
  if (btnOpenSettings) {
    btnOpenSettings.textContent = t.desktopOpenSettings;
    btnOpenSettings.hidden = false;
    btnOpenSettings.onclick = () => {
      desktop()?.permissions?.open(PERMISSION.systemAudio);
    };
  }
  currentBackend = 'mic-only';
  if (nativePcmUnsub) {
    try {
      nativePcmUnsub();
    } catch {
      /* ignore */
    }
    nativePcmUnsub = null;
  }
  notifyShell();
}

function formatTimer(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const mins = String(Math.floor(total / 60)).padStart(2, '0');
  const secs = String(total % 60).padStart(2, '0');
  return `${mins}:${secs}`;
}

function updateLiveChipClock() {
  if (!liveChipEl || !listening || !timerEl) return;
  timerEl.textContent = transcriptionOffline
    ? strings(uiLang()).desktopOffline
    : formatTimer(Date.now() - startedAt);
}

function loseSession() {
  if (listening) stopCapture();
  localStorage.removeItem(STORAGE.token);
  localStorage.removeItem(STORAGE.refresh);
  if (accountMenu) accountMenu.hidden = true;
  if (sessionChip) sessionChip.textContent = '';
  showScreen('login');
  notifyShell();
}

async function loadLocalPendingCaptures() {
  const cap = desktop()?.capture;
  if (!cap?.pending) return [];
  try {
    const result = await cap.pending();
    return Array.isArray(result?.items) ? result.items : [];
  } catch {
    return [];
  }
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
  const cards = homeHoyCardsForDisplay({captureActive: listening, cards: homeHoyListedItems(homeHoyItems, homeHoyActed, nowMs).map(todayItemToCard)});
  homeHoyEl.replaceChildren();
  homeHoyEl.hidden = listening;
  const status = document.getElementById('today-status');
  const incomplete = homeHoyCoverage && (!Object.keys(homeHoyCoverage).length || Object.values(homeHoyCoverage).some(value => value !== 'complete'));
  status.textContent = homeHoyError ? copy().todayError : homeHoyStale ? copy().loading : incomplete ? copy().incomplete : cards.length ? '' : `${copy().empty} ${copy().emptyHint}`;
  status.hidden = !status.textContent;
  document.getElementById('today-retry').hidden = !homeHoyError && !incomplete;
  for (const card of cards) {
    const t = strings(uiLang());
    const wrap = document.createElement('div');
    wrap.innerHTML = renderToString(renderTodayCard(card, {now: nowMs, dismiss:t.dismiss, undo:t.undo}));
    const article = wrap.firstElementChild;
    if (!card.canDismiss) article.querySelector('[data-action="dismiss"]')?.remove();
    const identity = document.createElement('p'); identity.className = 'today-identity'; identity.textContent = card.contactName || copy().unnamed;
    if (card.companyName) {const company=document.createElement('span');company.className='today-company';company.textContent=card.companyName;identity.append(company);}
    article.prepend(identity);
    const actions=document.createElement('div'); actions.className='today-actions';
    if (card.openUrl) {
      const open=document.createElement('button'); open.type='button'; open.className='primary'; open.textContent=copy().open;
      open.addEventListener('click',()=>desktop()?.shell?.openExternal(card.openUrl)); actions.append(open);
    } else {const hint=document.createElement('span');hint.className='muted';hint.textContent=copy().noTarget;actions.append(hint);}
    for (const action of article.querySelectorAll('button[data-action]')) {action.className='ghost'; actions.append(action);}
    article.append(actions);homeHoyEl.append(article);
  }
  if (cards.some(card => card.undoDeadline && Date.parse(card.undoDeadline)>=nowMs)) startHomeHoyUndoClock(); else stopHomeHoyUndoClock();
  if (shouldFetchHomeHoy({token,captureActive:listening,inFlight:homeHoyFlight,stale:homeHoyStale}) && !homeHoyError) {
    homeHoyFlight=true;
    request(homeHoyRequestPath(),{token}).then(body=>{
      if (localStorage.getItem(STORAGE.token)!==token) return;
      homeHoyItems=Array.isArray(body?.items)?body.items:[];
      homeHoyCoverage=body?.coverage || {};
      homeHoyFlight=false;homeHoyStale=false;paintHomeHoy();
    }).catch(()=>{
      if (localStorage.getItem(STORAGE.token)!==token) return;
      homeHoyFlight=false;homeHoyError=true;paintHomeHoy();
    });
  }
}

document.getElementById('today-retry').addEventListener('click',()=>{
  homeHoyError=false;homeHoyStale=true;paintHomeHoy();
});

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
    showError(listenError, copy().todayError);
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
    showError(listenError, copy().todayError);
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
      homeBriefCache = { contactId, brief: { text: copy().briefError, lines: [] } };
      homeBriefFlight = null;
      paintHomeBrief();
    });
}

async function paintNotesList() {
  if (!notesListEl) return;
  const token = localStorage.getItem(STORAGE.token);
  if (!token) {
    notesCache = [];
    localPendingCaptures = [];
    notesListEl.replaceChildren();
    return;
  }
  localPendingCaptures = await loadLocalPendingCaptures();
  try {
    const body = await request(notesRequestPath(), { token });
    notesCache = Array.isArray(body) ? body : [];
  } catch {
    notesCache = [];
  }
  const rows = noteRows(notesCache, { lang: uiLang() });
  notesListEl.replaceChildren();
  const pendingSorted = [...localPendingCaptures].sort((a, b) => {
    const ta = Date.parse(a.startedAt || '') || 0;
    const tb = Date.parse(b.startedAt || '') || 0;
    return tb - ta;
  });
  for (const capture of pendingSorted) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.dataset.localCapture = capture.clientCaptureId;
    const title = document.createElement('span');
    title.className = 'row-title';
    title.textContent = pendingCaptureSendLabel();
    const dot = document.createElement('span');
    dot.className = 'pending-dot';
    dot.setAttribute('aria-hidden', 'true');
    title.append(dot);
    const meta = document.createElement('span');
    meta.className = 'meta';
    const when = capture.startedAt
      ? new Date(capture.startedAt).toLocaleString(uiLang() === 'en' ? 'en-GB' : 'es-ES', {
          day: 'numeric',
          month: 'short',
          hour: '2-digit',
          minute: '2-digit',
        })
      : '';
    meta.textContent = when;
    btn.append(title, meta);
    notesListEl.append(btn);
  }
  for (const row of rows) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.dataset.id = row.id;
    const title = document.createElement('span');
    title.className = 'row-title';
    title.textContent = row.title;
    if (row.pending) {
      const dot = document.createElement('span');
      dot.className = 'pending-dot';
      dot.setAttribute('aria-hidden', 'true');
      title.append(dot);
    }
    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = [row.when, row.durationLabel].filter(Boolean).join(' · ');
    btn.append(title, meta);
    if (row.statusLabel) {
      const state = document.createElement('span');
      state.className = 'note-status';
      state.textContent = row.statusLabel;
      btn.append(state);
    }
    const labelParts = [row.title, row.when, row.durationLabel, row.statusLabel].filter(Boolean);
    if (labelParts.length) btn.setAttribute('aria-label', labelParts.join(', '));
    notesListEl.append(btn);
  }
}

function notifyShell() {
  const email = localStorage.getItem(STORAGE.email) || '';
  const loggedIn = Boolean(localStorage.getItem(STORAGE.token));
  if (accountMenu) {
    accountMenu.hidden = !loggedIn;
    if (!loggedIn) accountMenu.open = false;
  }
  if (sessionChip) sessionChip.textContent = loggedIn ? email : '';
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
  btnRecord.classList.toggle('live', on);
  listenPanel?.classList.toggle('is-live', on);
  btnRecord.setAttribute('aria-label', on ? copy().stop : copy().listen);
  document.getElementById('record-label').textContent = on ? copy().stop : copy().listen;
  document.getElementById('home-context').hidden = on;
  document.getElementById('record-hint').hidden = on;
  if (liveChipEl) liveChipEl.hidden = !on;
  if (assistToggleEl) assistToggleEl.hidden = !on;
  if (idleBlockEl) idleBlockEl.hidden = on;
  if (!on && transcriptEl) transcriptEl.replaceChildren();
  if (on) {
    startedAt = Date.now();
    timerEl.textContent = '00:00';
    clearInterval(timerTick);
    timerTick = setInterval(() => {
      updateLiveChipClock();
    }, 250);
  } else {
    clearInterval(timerTick);
    timerTick = null;
    if (assistInputEl) assistInputEl.checked = false;
  }
}

function highlightActiveNote(id) {
  notesListEl?.querySelectorAll('button[data-id]').forEach((btn) => {
    btn.setAttribute('aria-current', id != null && btn.dataset.id === String(id) ? 'true' : 'false');
  });
}

function showScreen(name) {
  loginPanel.hidden = name !== 'login';
  if (permissionsPanel) permissionsPanel.hidden = name !== 'permissions';
  listenPanel.hidden = name !== 'listen';
  reviewPanel.hidden = name !== 'review';
  if (notesRailEl) notesRailEl.hidden = name === 'login' || name === 'permissions';
  if (accountMenu) accountMenu.hidden = name === 'login' || !localStorage.getItem(STORAGE.token);
  desktop()?.shell?.resize(name === 'review' ? 'review' : 'compact');
  if (name === 'listen') {
    if (!listening) setLiveUi(false);
    paintListenPermissionGate();
    syncPermissionPoll();
    paintHomeBrief();
    paintHomeHoy();
    highlightActiveNote(null);
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

function needsMacPermissions() {
  const platform = permissionState.platform || desktop()?.platform;
  return platform === 'darwin';
}

function permissionRowCopy(type, on) {
  const c = copy();
  if (type === PERMISSION.microphone) {
    return {
      title: on ? c.permMicOn : c.permMicEnable,
      body: on ? c.permMicOnBody : c.permMicBody,
    };
  }
  return {
    title: on ? c.permAudioOn : c.permAudioEnable,
    body: on ? c.permAudioOnBody : c.permAudioBody,
  };
}

function paintPermissionRow(row, type, status) {
  if (!row) return;
  const on = status === 'authorized';
  const labels = permissionRowCopy(type, on);
  row.classList.toggle('is-on', on);
  row.querySelector('[data-title]').textContent = labels.title;
  row.querySelector('[data-body]').textContent = labels.body;
  const btn = row.querySelector('[data-action]');
  if (!btn) return;
  btn.hidden = on;
  const action = permissionAction(status);
  btn.textContent = action === 'open_settings' ? copy().permOpenSettings : copy().permEnable;
  btn.dataset.permType = type;
}

function paintAllPermissionRows() {
  for (const row of document.querySelectorAll('.perm-row[data-perm]')) {
    const type = row.dataset.perm === 'microphone' ? PERMISSION.microphone : PERMISSION.systemAudio;
    const status =
      type === PERMISSION.microphone ? permissionState.microphone : permissionState.systemAudio;
    paintPermissionRow(row, type, status);
  }
  const cont = document.getElementById('btn-permissions-continue');
  if (cont) cont.disabled = !permissionGate().ok;
  paintListenPermissionGate();
}

function paintListenPermissionGate() {
  const mac = needsMacPermissions();
  const gateOk = permissionGate().ok;
  if (listenPermissionsEl) listenPermissionsEl.hidden = !mac || gateOk || listening;
  if (recordHint) recordHint.hidden = mac && !gateOk;
  if (btnRecord) btnRecord.disabled = mac && !gateOk && !listening;
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

function markMacPermissionsReadyIfNeeded() {
  if (permissionGate().ok) {
    localStorage.setItem(STORAGE.macPermissionsReady, '1');
  }
}

function syncPermissionPoll() {
  const mac = needsMacPermissions();
  const onListen = listenPanel && !listenPanel.hidden;
  if (mac && onListen && !permissionGate().ok) startPermissionPoll();
  else stopPermissionPoll();
}

async function refreshPermissions() {
  const api = desktop()?.permissions;
  if (!api?.status) {
    permissionState = applyPermissionSnapshot(null, { platform: desktop()?.platform || 'darwin' });
    permissionState.microphone = 'authorized';
    permissionState.systemAudio = 'authorized';
    paintAllPermissionRows();
    markMacPermissionsReadyIfNeeded();
    syncPermissionPoll();
    return permissionState;
  }
  const raw = await api.status();
  permissionState = applyPermissionSnapshot(raw, { platform: desktop()?.platform || 'darwin' });
  paintAllPermissionRows();
  markMacPermissionsReadyIfNeeded();
  syncPermissionPoll();
  return permissionState;
}

async function handlePermissionClick(type) {
  const api = desktop()?.permissions;
  if (!api) return;
  const status = type === PERMISSION.microphone ? permissionState.microphone : permissionState.systemAudio;
  if (permissionAction(status) === 'open_settings') await api.open(type);
  else await api.request(type);
  await refreshPermissions();
}

async function enterApp() {
  await refreshPermissions();
  showScreen('listen');
  setLiveUi(false);
  paintListenPermissionGate();
  notifyShell();
  void paintNotesList();
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
        if (path !== '/auth/login' && isSessionError({ status: result.status, detail })) {
          loseSession();
        }
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
      if (path !== '/auth/login' && isSessionError({ status: res.status, detail })) {
        loseSession();
      }
      throw new Error(detail);
    }
    return data;
  } catch (err) {
    throw new Error(humanizeSaasError(err, { detail: err?.message }));
  }
}

let stickToLive = true;

function noteFromMemoTranscript(text) {
  const body = String(text || '').trim();
  if (!body) return emptyNote();
  return { turns: [{ speaker: '', committed: body, live: '' }] };
}

function renderLiveNoteInto(container, note, { emptyMessage = '' } = {}) {
  if (!container) return false;
  const t = strings(uiLang());
  const turns = note.turns;
  const hasContent = turns.some((turn) => turn.committed || turn.live);
  if (!hasContent) {
    container.querySelectorAll('.v-transcript-turn').forEach((node) => node.remove());
    if (emptyMessage && !container.querySelector('.empty')) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = emptyMessage;
      container.append(empty);
    }
    return false;
  }
  container.querySelector('.empty')?.remove();
  const rows = [...container.querySelectorAll('.v-transcript-turn')];
  turns.forEach((turn, index) => {
    let row = rows[index];
    if (!row) {
      row = document.createElement('div');
      row.className = 'v-transcript-turn';
      const speaker = document.createElement('span');
      speaker.className = 'speaker';
      const committed = document.createElement('span');
      committed.className = 'committed';
      const live = document.createElement('span');
      live.className = 'live';
      row.append(speaker, committed, live);
      container.append(row);
    }
    const speakerEl = row.children[0];
    const committedEl = row.children[1];
    const liveEl = row.children[2];
    const speakerLabel =
      turn.speaker === 'rep' ? t.speakerYou : turn.speaker === 'prospect' ? t.speakerThem : '';
    if (speakerEl.textContent !== speakerLabel) speakerEl.textContent = speakerLabel;
    if (committedEl.textContent !== turn.committed) committedEl.textContent = turn.committed;
    if (liveEl.textContent !== turn.live) liveEl.textContent = turn.live;
  });
  rows.slice(turns.length).forEach((node) => node.remove());
  return true;
}

function paintReviewNote(note) {
  if (!reviewNoteEl) return;
  renderLiveNoteInto(reviewNoteEl, note);
  reviewNoteEl.scrollTop = 0;
}

function setReviewLoading(loading) {
  if (loading) reviewPanel.dataset.loading = 'true';
  else delete reviewPanel.dataset.loading;
  const summaryEl = document.getElementById('review-summary');
  const nextEl = document.getElementById('review-next');
  const fieldsEl = document.getElementById('review-fields');
  const dealEl = document.getElementById('review-deal');
  const dealsEl = document.getElementById('review-deals');
  const checklistEl = document.getElementById('review-checklist');
  summaryEl.classList.toggle('review-slot', loading);
  nextEl.classList.toggle('review-slot', loading);
  if (loading) {
    summaryEl.value = '';
    nextEl.value = '';
    fieldsEl.replaceChildren();
    for (let i = 0; i < 2; i += 1) {
      const slot = document.createElement('div');
      slot.className = 'review-slot';
      fieldsEl.append(slot);
    }
    dealEl.textContent = '';
    dealEl.classList.add('review-slot');
    dealsEl.hidden = true;
    followupEl.hidden = true;
    document.getElementById('followup-error').hidden = true;
    document.getElementById('followup-retry').hidden = true;
    if (checklistEl) checklistEl.hidden = true;
    document.getElementById('btn-approve').hidden = true;
    if (btnReviewDashboard) btnReviewDashboard.hidden = true;
  } else {
    dealEl.classList.remove('review-slot');
  }
}

function hideReviewRetry() {
  if (btnReviewRetry) btnReviewRetry.hidden = true;
}

function showReviewPrepareFailure() {
  const t = strings(uiLang());
  showError(reviewError, t.desktopPrepareFailed);
  if (btnReviewRetry && (pendingReviewTranscript || reviewRetryMemoId)) {
    btnReviewRetry.hidden = false;
    btnReviewRetry.textContent = t.desktopRetry;
  }
}

function clearReviewRetryState() {
  pendingReviewTranscript = null;
  reviewRetryMemoId = null;
  reviewRetryReadOnly = false;
  reviewRetryCaptureId = null;
  reviewRetryDurationSec = null;
}

function renderTranscript() {
  const t = strings(uiLang());
  const follow = stickToLive;
  const hasContent = renderLiveNoteInto(transcriptEl, liveNote, { emptyMessage: '' });
  if (returnLiveBtn) {
    returnLiveBtn.hidden = follow || !hasContent;
    returnLiveBtn.textContent = t.transcriptBackToLive;
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
  if (nativeLostUnsub) {
    try { nativeLostUnsub(); } catch { /* ignore */ }
    nativeLostUnsub = null;
  }
  const native = desktop()?.systemAudio;
  if (native?.stop) {
    Promise.resolve(native.stop()).catch(() => {});
  }
  closeTranscriptionWebSocket(true);
  transcriptionOffline = false;
  wsReconnectAttempts = 0;
  clientCaptureId = null;
  serverCaptureMemoId = null;
  if (audioContext) {
    audioContext.close().catch(() => {});
    audioContext = null;
  }
  setLiveUi(false);
  desktop()?.shell?.hideOverlay();
  paintHomeBrief();
  homeHoyStale = true;
  paintHomeHoy();
  notifyShell();
}

function appendCaptureAudio(channel, pcm) {
  const cap = desktop()?.capture;
  if (!cap?.append || !clientCaptureId) return;
  const storeChannel = channel === 'rep' ? 'mic' : 'system';
  void cap.append({
    clientCaptureId,
    channel: storeChannel,
    chunk: [...new Uint8Array(pcm)],
  });
}

function clearWsReconnectTimer() {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }
}

function closeTranscriptionWebSocket(intentional = true) {
  wsIntentionalClose = intentional;
  clearWsReconnectTimer();
  if (websocket) {
    try {
      if (websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({ type: 'CloseStream' }));
      }
      websocket.close();
    } catch { /* ignore */ }
    websocket = null;
  }
}

function scheduleTranscriptionReconnect() {
  if (!listening || wsIntentionalClose || wsReconnectAttempts >= 5) return;
  wsReconnectAttempts += 1;
  clearWsReconnectTimer();
  wsReconnectTimer = setTimeout(() => {
    wsReconnectTimer = null;
    if (!listening || wsIntentionalClose) return;
    openTranscriptionWebSocket();
  }, 2000);
}

function openTranscriptionWebSocket() {
  const wsUrl = applyChannelLabelsToLiveUrl(liveTranscriptionUrl(apiBase()), ['prospect', 'rep']);
  websocket = new WebSocket(wsUrl);
  websocket.onopen = () => {
    wsReconnectAttempts = 0;
    transcriptionOffline = false;
    updateLiveChipClock();
  };
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
      const speaker =
        data.audio_channel === 'rep' ? 'rep' : data.audio_channel === 'prospect' ? 'prospect' : '';
      liveNote = applyChunk(liveNote, { text, isFinal, speaker });
      if (isFinal) {
        const latestTurn = latestFinal(liveNote);
        void requestCopilotSuggest(latestTurn);
        void requestCopilotChecklist();
      }
      renderTranscript();
    } catch { /* ignore malformed frames */ }
  };
  websocket.onerror = () => {
    transcriptionOffline = true;
    updateLiveChipClock();
  };
  websocket.onclose = () => {
    if (!listening || wsIntentionalClose) return;
    transcriptionOffline = true;
    updateLiveChipClock();
    scheduleTranscriptionReconnect();
  };
}

async function startListen() {
  await refreshPermissions();
  const gate = canStartListen({
    hasToken: Boolean(localStorage.getItem(STORAGE.token)),
    isListening: listening,
    permissionGate: permissionGate(),
  });
  if (!gate.ok) {
    showListenDenied(gate.reason, desktop()?.platform);
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
    showListenDenied('no_mic', platform);
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
      showListenDenied('no_system_audio', platform);
      return;
    }
    if (!system.getAudioTracks().length) {
      mic.getTracks().forEach((t) => t.stop());
      system.getTracks().forEach((t) => t.stop());
      showListenDenied('no_system_audio', platform);
      return;
    }
  }

  listening = true;
  wsIntentionalClose = false;
  wsReconnectAttempts = 0;
  transcriptionOffline = false;
  clientCaptureId = crypto.randomUUID();
  const captureStartedAt = new Date().toISOString();
  serverCaptureMemoId = null;
  const cap = desktop()?.capture;
  if (cap?.begin) {
    void cap.begin({ clientCaptureId, startedAt: captureStartedAt });
  }
  currentBackend = nativeBackend || 'chromium';
  captureStreams = system ? [mic, system] : [mic];
  hubspotRecordPage = knownHubspotRecordPage() ?? hubspotRecordPage;
  listenSession = buildListenSession({
    callMode: 'meeting',
    crmPageContext: hubspotRecordPage,
  });
  const activeClientCaptureId = clientCaptureId;
  const token = localStorage.getItem(STORAGE.token);
  void reserveDesktopCapture(
    (path, opts) => request(path, { ...opts, token }),
    {
      clientCaptureId: activeClientCaptureId,
      startedAt: captureStartedAt,
    },
  )
    .then((data) => {
      if (!listening || clientCaptureId !== activeClientCaptureId) return;
      serverCaptureMemoId = data.capture_id;
      listenSession = buildListenSession({
        callMode: 'meeting',
        crmPageContext: hubspotRecordPage,
        captureId: data.capture_id,
      });
      void requestCopilotChecklist();
    })
    .catch(() => {
      /* mic capture continues; live checklist stays on company playbook until reserve succeeds */
    });
  const listenAssist = beginMeetingListenAssist({ createMeetingId: () => crypto.randomUUID() });
  liveAssistMeetingId = listenAssist.meetingId;
  Object.assign(liveAssistOverlay, listenAssist.overlay);
  liveAssistChecklist = listenAssist.checklist;
  transcriptState = { finalTranscript: '', interimTranscript: '' };
  liveNote = emptyNote();
  if (listenAssist.resetSuggestDedupe) resetCopilotSuggestRequestDedupe();
  resetSuggestProfileProductContextCache();
  renderTranscript();
  setLiveUi(true);
  desktop()?.shell?.showOverlay();
  paintHomeBrief();
  paintHomeHoy();
  notifyShell();

  openTranscriptionWebSocket();

  audioContext = new AudioContext({ sampleRate: 16000 });
  const send = (channel) => (pcm) => {
    appendCaptureAudio(channel, pcm);
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.send(encodeChannelAudio(channel, pcm));
    }
  };
  hookPcm(audioContext, mic, send('rep'));
  if (system) {
    hookPcm(audioContext, system, send('prospect'));
  } else if (native?.onPcm) {
    nativePcmUnsub = native.onPcm((pcm) => send('prospect')(pcm));
    if (native.onLost) {
      nativeLostUnsub = native.onLost(() => {
        if (!listening) return;
        if (currentBackend !== 'screencapturekit' && currentBackend !== 'sck') return;
        showMeetingAudioLost();
      });
    }
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
  summaryEl.classList.remove('review-slot');
  nextEl.classList.remove('review-slot');
  summaryEl.value = ctx.summary ?? notes.summary;
  nextEl.value = (ctx.nextSteps || notes.nextSteps).join('\n');
  summaryEl.readOnly = ctx.readOnly;
  nextEl.readOnly = ctx.readOnly;
  const approveBtn = document.getElementById('btn-approve');
  approveBtn.hidden = ctx.readOnly;
  if (btnReviewDashboard) {
    btnReviewDashboard.hidden = !ctx.readOnly;
    if (ctx.readOnly) {
      btnReviewDashboard.textContent = strings(uiLang()).desktopOpenDashboard;
    }
  }
  const dealEl = document.getElementById('review-deal');
  const dealsEl = document.getElementById('review-deals');
  if (ctx.deal.needsDecision) {
    dealEl.textContent = copy().selectDeal;
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
    text.textContent = copy().newDeal;
    create.append(text, radio);
    dealsEl.appendChild(create);
  } else {
    dealsEl.hidden = true;
    dealEl.textContent = ctx.deal.selected
      ? `${copy().matched}: ${ctx.deal.selected.deal_name || ctx.deal.selected.deal_id}`
      : copy().noDeal;
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
    input.disabled = ctx.readOnly;
    input.addEventListener('input', () => {
      row.new_value = input.value;
    });
    block.appendChild(input);
    wrap.appendChild(block);
    if (!ctx.readOnly && canEditOrRemoveProposedField(row)) {
      const omit = document.createElement('button');
      omit.type = 'button';
      omit.className = 'ghost omit';
      omit.textContent = copy().omit;
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
    const empty=document.createElement('p');empty.className='muted';empty.textContent=copy().noFields;fieldsEl.append(empty);
  }
  document.getElementById('review-fields-label').textContent = `${copy().fields} · ${ctx.updates.length}`;
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
    if (reviewContext?.memoId !== memoId) return;
    followupEl.hidden = true;
    showError(document.getElementById('followup-error'), copy().followupError);
    document.getElementById('followup-retry').hidden = false;
    return;
  }
  document.getElementById('followup-error').hidden = true;
  document.getElementById('followup-retry').hidden = true;
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
    showError(reviewError, err.message || copy().followupError);
  }
});

async function populateReviewContext(memoId, { readOnly = false } = {}) {
  const generation = ++reviewLoadGeneration;
  const token = localStorage.getItem(STORAGE.token);
  document.getElementById('review-status').textContent = copy().preparing;
  const waited = await waitForReview(() => request(`/memos/${memoId}`, { token }));
  if (generation !== reviewLoadGeneration) return;
  if (!waited.ok) {
    document.getElementById('review-status').textContent = '';
    throw new Error(waited.error || 'Extraction failed');
  }
  const memo = waited.memo;
  let preview = {};
  preview = await request(`/memos/${memoId}/preview`, { token });
  if (generation !== reviewLoadGeneration) return;
  readOnly = readOnly || memo.status === 'approved';
  const deal = pickDeal(preview.matched_deals || preview.matches || []);
  const notes = notesFromPreview(preview, memo.extraction);
  reviewContext = {
    memoId,
    memo,
    preview,
    deal,
    dealId: deal.dealId,
    isNewDeal: false,
    readOnly,
    originalUpdates: reviewFields(preview),
    updates: reviewFields(preview).map((row) => ({ ...row })),
    omittedKeys: [],
    summary: notes.summary,
    nextSteps: notes.nextSteps,
    meetingChecklist: null,
  };
  if (!reviewNoteSnapshot) {
    paintReviewNote(noteFromMemoTranscript(memo.transcript));
  }
  document.getElementById('review-status').textContent = readOnly
    ? copy().saved
    : copy().needsReview;
  setReviewLoading(false);
  paintReviewChecklist(null);
  loadFollowup(memoId, token);
  renderReview();
  void loadReviewChecklist(memoId, token);
}

async function uploadAndOpenReview(
  transcript,
  { note = liveNote, durationSec = null, captureId = null } = {},
) {
  const token = localStorage.getItem(STORAGE.token);
  const authedRequest = (path, opts) => request(path, { ...opts, token });
  let memoId = null;
  if (captureId) {
    const completed = await completeDesktopCapture(authedRequest, {
      captureId,
      transcript,
      duration: durationSec,
      turns: note?.turns ?? [],
    });
    memoId = completed.memo_id || completed.capture_id;
  } else {
    const uploaded = await request('/memos/upload-and-extract', {
      method: 'POST',
      token,
      body: { transcript, source_type: 'meeting_transcript' },
    });
    memoId = uploaded.id;
  }
  void paintNotesList();
  pendingReviewTranscript = null;
  reviewRetryMemoId = String(memoId);
  reviewRetryReadOnly = false;
  await populateReviewContext(memoId);
  clearReviewRetryState();
  hideReviewRetry();
}

async function openReview(memoId, { readOnly = false } = {}) {
  pendingReviewTranscript = null;
  reviewRetryMemoId = String(memoId);
  reviewRetryReadOnly = readOnly;
  showScreen('review');
  highlightActiveNote(memoId);
  showError(reviewError, '');
  hideReviewRetry();
  if (String(reviewContext?.memoId) !== String(memoId)) {
    reviewNoteSnapshot = null;
  }
  setReviewLoading(true);
  try {
    await populateReviewContext(memoId, { readOnly });
    clearReviewRetryState();
    hideReviewRetry();
  } catch {
    setReviewLoading(false);
    showReviewPrepareFailure();
  }
}

async function stopAndSend() {
  const t = strings(uiLang());
  const noteForUpload = liveNote;
  const transcript = noteUploadText(noteForUpload, { you: t.speakerYou, them: t.speakerThem }).trim();
  const durationSec =
    startedAt > 0 ? Math.max(0, Math.round((Date.now() - startedAt) / 1000)) : null;
  const reservedCaptureId = serverCaptureMemoId;
  reviewNoteSnapshot = noteForUpload;
  stopCapture();
  if (!transcript) {
    reviewNoteSnapshot = null;
    showError(listenError, t.desktopNothingHeard);
    return;
  }
  pendingReviewTranscript = transcript;
  reviewRetryMemoId = null;
  reviewRetryReadOnly = false;
  reviewRetryCaptureId = reservedCaptureId;
  reviewRetryDurationSec = durationSec;
  showScreen('review');
  paintReviewNote(reviewNoteSnapshot);
  setReviewLoading(true);
  showError(reviewError, '');
  hideReviewRetry();
  try {
    await uploadAndOpenReview(transcript, {
      note: noteForUpload,
      durationSec,
      captureId: reservedCaptureId,
    });
  } catch {
    setReviewLoading(false);
    showReviewPrepareFailure();
  }
}

async function approveReview() {
  if (!reviewContext || reviewContext.readOnly) return;
  if (reviewContext.deal.needsDecision && !reviewContext.dealId && !reviewContext.isNewDeal) { showError(reviewError, copy().confirmFirst); return; }
  const approvingContext = reviewContext;
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
    if (reviewContext !== approvingContext) return;
    reviewContext.readOnly = true;
    document.getElementById('review-status').textContent = copy().saved;
    renderReview();
    void paintNotesList();
  } catch (err) {
    showError(reviewError, err.message || copy().confirmError);
  } finally {
    document.getElementById('btn-approve').disabled = false;
  }
}

document.getElementById('btn-permissions-continue')?.addEventListener('click', () => {
  if (permissionGate().ok) {
    stopPermissionPoll();
    showScreen('listen');
    setLiveUi(false);
    void paintNotesList();
  }
});

document.addEventListener('click', (event) => {
  const btn = event.target.closest('.perm-row [data-action]');
  if (!btn || btn.hidden) return;
  const type = btn.dataset.permType;
  if (type === PERMISSION.microphone || type === PERMISSION.systemAudio) {
    handlePermissionClick(type).catch(() => {});
  }
});

document.getElementById('btn-login').addEventListener('click', async () => {
  showError(loginError, '');
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
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
  homeHoyError = false; homeHoyCoverage = null; homeHoyFlight = false;
  homeHoyActed = [];
  homeHoyStale = true;
  notesCache = [];
  notesListEl?.replaceChildren();
  localStorage.removeItem(STORAGE.token);
  localStorage.removeItem(STORAGE.refresh);
  if (accountMenu) accountMenu.hidden = true;
  if (sessionChip) sessionChip.textContent = '';
  showScreen('login');
  notifyShell();
});

document.getElementById('btn-dashboard').addEventListener('click', () => {
  desktop()?.shell?.openExternal(dashboardMemosUrl(apiBase()));
});

document.getElementById('btn-new-note').addEventListener('click', () => {
  showScreen('listen');
});

notesListEl?.addEventListener('click', (event) => {
  if (listening) return;
  if (event.target.closest('button[data-local-capture]')) return;
  const btn = event.target.closest('button[data-id]');
  if (!btn) return;
  const id = btn.dataset.id;
  const memo = notesCache.find((m) => String(m.id) === id);
  openReview(id, { readOnly: memo?.status === 'approved' }).catch((err) =>
    showError(reviewError, err.message || 'Could not open note'),
  );
});

transcriptEl.addEventListener('scroll', () => {
  stickToLive = scrollFollow({
    scrollTop: transcriptEl.scrollTop,
    scrollHeight: transcriptEl.scrollHeight,
    clientHeight: transcriptEl.clientHeight,
  }).follow;
  if (returnLiveBtn) returnLiveBtn.hidden = stickToLive || !transcriptEl.querySelector('.v-transcript-turn');
});
returnLiveBtn?.addEventListener('click', () => {
  stickToLive = true;
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
  returnLiveBtn.hidden = true;
});

btnRecord.addEventListener('click', () => {
  if (listening) {
    stopAndSend().catch((err) => showError(listenError, err.message || 'Could not stop'));
  } else {
    startListen().catch((err) =>
      showError(listenError, err.message || strings(uiLang()).listenCouldNotStart),
    );
  }
});
assistInputEl?.addEventListener('change', () => {
  desktop()?.shell?.command(assistInputEl.checked ? 'assist-on' : 'assist-off');
});
document.getElementById('btn-approve').addEventListener('click', () => {
  approveReview().catch((err) => showError(reviewError, err.message || copy().confirmError));
});
btnReviewRetry?.addEventListener('click', () => {
  if (pendingReviewTranscript) {
    const transcript = pendingReviewTranscript;
    setReviewLoading(true);
    showError(reviewError, '');
    hideReviewRetry();
    uploadAndOpenReview(transcript, {
      note: reviewNoteSnapshot || liveNote,
      durationSec: reviewRetryDurationSec,
      captureId: reviewRetryCaptureId,
    }).catch(() => {
      setReviewLoading(false);
      if (reviewRetryMemoId) {
        pendingReviewTranscript = null;
      } else {
        pendingReviewTranscript = transcript;
      }
      showReviewPrepareFailure();
    });
    return;
  }
  if (reviewRetryMemoId) {
    openReview(reviewRetryMemoId, { readOnly: reviewRetryReadOnly }).catch(() => {});
  }
});

btnReviewDashboard?.addEventListener('click', () => {
  const memoId = reviewContext?.memoId;
  if (!memoId) return;
  desktop()?.shell?.openExternal(`${dashboardMemosUrl(apiBase())}/${memoId}`);
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
    if (assistInputEl) assistInputEl.checked = true;
    notifyShell();
    const latestTurn = latestFinal(liveNote);
    if (latestTurn) void requestCopilotSuggest(latestTurn);
  }
  if (command === 'assist-off') {
    const off = turnOffLiveAssist(liveAssistOverlay);
    if (assistInputEl) assistInputEl.checked = false;
    if (off.shouldAbortSuggest) abortCopilotSuggest();
    notifyShell();
  }
});

document.getElementById('email').value = localStorage.getItem(STORAGE.email) || '';

async function boot() {
  const token = localStorage.getItem(STORAGE.token);
  let meOk = false;
  if (token) {
    try {
      await request('/auth/me', { token });
      meOk = true;
    } catch {
      meOk = false;
    }
  }
  const screen = startScreen({
    hasToken: Boolean(localStorage.getItem(STORAGE.token)),
    meOk,
  });
  if (screen === 'listen') await enterApp();
  else showScreen('login');
}

window.__vocifyBooted = true;
void boot();

document.addEventListener('click', (event) => {
  if (accountMenu && !accountMenu.contains(event.target)) accountMenu.open = false;
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && accountMenu?.open) {
    accountMenu.open = false;
    sessionChip.focus();
  }
});

document.getElementById('followup-retry').addEventListener('click', () => {
  if (reviewContext) void loadFollowup(reviewContext.memoId, localStorage.getItem(STORAGE.token));
});
