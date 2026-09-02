/**
 * Service Worker for Vocify Chrome Extension
 * 
 * The "Brain" of the extension. Maintains state even when popup is closed.
 */

import { api } from './lib/api.js';
import { CALL_STATES, canStartCall, normalizeDialTarget } from './lib/dialer.js';
import { isAuthFailure, isCrmReconnectError } from './lib/auth-session.js';
import { parseHubSpotUrl } from './lib/hubspot-parser.js';
import { pickContextTab } from './lib/review-targets.js';
import { planPageContextUpdate, recordScopeKey, recordingsScopeKey } from './lib/page-scope.js';
import { planRecordingsFetch, planRecordingsResult } from './lib/recordings-fetch.js';
import { memoListFromResponse } from './lib/activity-list.js';
import {
  applyTranscriptUpdate,
  canStartTabCapture,
  isListenEpochCurrent,
  listenFailureReason,
  listenReasonFromOffscreenError,
  requestTabCaptureStreamId,
  shouldApplyTabCaptureLifecycle,
  startDeniedMessage,
  tabCaptureOffscreenReasons,
} from './lib/tab-capture.js';
import { TurnDetector } from './lib/turn-detector.js';
import {
  DEFAULT_PRODUCT_CONTEXT,
  PRODUCT_CONTEXT_STORAGE_KEY,
} from './lib/copilot-sse.js';
import { COPILOT_CHANNEL_MODE, isCoachableChannel } from './lib/stt-channels.js';
import { mergeSessionVocab } from './lib/session-vocab.js';
import { apiBaseToWsOrigin } from './lib/api-base.js';
import { actionsForCommand } from './lib/hotkey.js';
import { reviewMemoIfCurrent, slimReviewMemo } from './lib/review-screen.js';
import { reviewIdsFromMemo } from './lib/memo-identity.js';
import {
  clearInflightPreview,
  clearPreviewCache,
  getCachedPreview,
  getInflightPreview,
  previewCacheKey,
  setCachedPreview,
  setInflightPreview,
} from './lib/preview-cache.js';

const OFFSCREEN_DOCUMENT_PATH = 'offscreen.html';

// ============================================
// CENTRAL STATE (Source of Truth)
// ============================================
let state = {
  isRecording: false,
  isCopilotListening: false,
  finalTranscript: '',
  interimTranscript: '',
  prospectFinal: '',
  prospectInterim: '',
  finalWords: [],
  currentMemoId: null,
  status: 'idle', // idle, recording, copilot, processing, review, success
  context: null,
  syncResult: null,
  processingSource: null, // 'hubspot_call' | null
  recordings: [],
  recordingsLoading: false,
  recordingsError: null,
  copilotSuggestion: null,
  copilotRawStream: '',
  copilotIsLoading: false,
  copilotLastTurn: null,
  copilotError: null,
  copilotLatencyMs: null,
  copilotTabTitle: null,
  captureTabId: null,
  listenPhase: 'idle',
  reviewMemo: null,
  call: {
    state: CALL_STATES.IDLE,
    to: null,
    callerId: null,
    error: null,
    callSid: null,
    answeredAt: null,
    muted: false,
    contactId: null,
    dealId: null,
  },
  lastCall: null,
};

/** Cached for sidePanel.open – must be called synchronously in user gesture, no await before it */
let lastActiveTabId = null;
/** Last recordings scope that finished (success or handled error). Not set at request start. */
let recordingsKey = null;
/** Scope of the in-flight recordings request, or null. */
let recordingsInFlightKey = null;
let recordingsFetchGen = 0;
/** Last URL we applied per tab — HubSpot SPA often updates url without changeInfo.url */
const lastSeenUrlByTab = new Map();

/**
 * Side panel / service worker have no "current window". Prefer the last HubSpot
 * tab we saw, then the last focused window — otherwise contact pages look like
 * the global inbox.
 */
async function getContextTab() {
  const candidates = [];

  for (const query of [
    { active: true, lastFocusedWindow: true },
    { active: true, currentWindow: true },
  ]) {
    try {
      const [tab] = await chrome.tabs.query(query);
      if (tab) candidates.push(tab);
    } catch (_) { /* continue */ }
  }

  if (lastActiveTabId != null) {
    try {
      candidates.push(await chrome.tabs.get(lastActiveTabId));
    } catch (_) {
      lastActiveTabId = null;
    }
  }

  try {
    const hubspotTabs = await chrome.tabs.query({ active: true, url: ['https://*.hubspot.com/*'] });
    candidates.push(...hubspotTabs);
  } catch (_) { /* host permission may be missing */ }

  const seen = new Set();
  const unique = [];
  for (const tab of candidates) {
    if (!tab?.id || seen.has(tab.id)) continue;
    seen.add(tab.id);
    unique.push(tab);
  }

  const chosen = pickContextTab(unique, { lastActiveTabId });
  if (chosen?.id != null) lastActiveTabId = chosen.id;
  return chosen;
}

function rememberTab(tab) {
  if (tab?.id != null) {
    lastActiveTabId = tab.id;
    state = { ...state, captureTabId: tab.id };
  }
}

let callWatchTimerId = null;
let callWatchingRecordId = null;  // deal or contact id being watched
let callWatchingRecordType = null; // 'deal' | 'contact' | 'company'
/** Interval for user-initiated memo processing (mic upload or Transcribe). */
let memoPollTimerId = null;
/** Memos the user dismissed. Never auto-open these. */
const ignoredCallMemoIds = new Set();

function requestMemoPreview({
  memoId,
  dealId = null,
  contactId = null,
  createNewDeal = false,
  extraction = null,
} = {}) {
  const key = previewCacheKey({ memoId, dealId, contactId, createNewDeal });
  if (!extraction) {
    const cached = getCachedPreview(key);
    if (cached) return Promise.resolve(cached);
    const inflight = getInflightPreview(key);
    if (inflight) return inflight;
  }
  const req = extraction
    ? api.post(`/memos/${memoId}/preview`, {
        deal_id: dealId || null,
        contact_id: contactId || null,
        create_new_deal: !!createNewDeal,
        extraction,
      })
    : (() => {
        const params = new URLSearchParams();
        if (dealId) params.set('deal_id', dealId);
        if (contactId) params.set('contact_id', contactId);
        if (createNewDeal) params.set('create_new_deal', 'true');
        const qs = params.toString();
        return api.get(`/memos/${memoId}/preview${qs ? `?${qs}` : ''}`);
      })();
  const pending = req
    .then((preview) => {
      if (preview && !preview.error) setCachedPreview(key, preview);
      return preview;
    })
    .finally(() => clearInflightPreview(key));
  if (!extraction) setInflightPreview(key, pending);
  return pending;
}

function prefetchReviewPreview(memoId, memo) {
  if (!memoId || !memo) return;
  const status = String(memo.status || '');
  if (status !== 'pending_review' && status !== 'approved') return;
  const ids = reviewIdsFromMemo(memo, {});
  requestMemoPreview({
    memoId,
    dealId: ids.dealId,
    contactId: ids.contactId,
    createNewDeal: false,
  }).catch(() => {});
}

function openReviewFromMemo(memoId, memo) {
  const slim = slimReviewMemo(memo);
  prefetchReviewPreview(memoId, slim);
  updateState({
    status: 'review',
    currentMemoId: memoId,
    reviewMemo: slim,
  });
}

// ============================================
// STATE MANAGEMENT
// ============================================
function updateState(newState) {
  if (newState.status === 'idle' || newState.status === 'success') {
    if (newState.reviewMemo === undefined) newState.reviewMemo = null;
    clearPreviewCache();
  }

  state = { ...state, ...newState, captureTabId: lastActiveTabId };
  state.reviewMemo = reviewMemoIfCurrent(state.reviewMemo, state.currentMemoId);

  if (state.listenPhase === 'live' || state.isCopilotListening) {
    chrome.action.setBadgeText({ text: 'LIVE' });
    chrome.action.setBadgeBackgroundColor({ color: '#C4A37A' });
  } else if (state.listenPhase === 'starting') {
    chrome.action.setBadgeText({ text: '…' });
    chrome.action.setBadgeBackgroundColor({ color: '#C4A37A' });
  } else {
    chrome.action.setBadgeText({ text: state.isRecording ? 'REC' : '' });
    if (state.isRecording) chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });
  }

  chrome.runtime.sendMessage({ type: 'STATE_UPDATED', state }).catch(() => {});
}

/**
 * Opens the extension UI. Must run synchronously in user gesture – no await before sidePanel.open.
 * Chrome expires the gesture in ~1ms; pre-fetched tabId avoids async gap.
 */
function openExtensionUI() {
  if (!chrome.sidePanel?.open) {
    showNotification('Vocify', 'Click the extension icon in the toolbar to open.');
    return;
  }

  if (lastActiveTabId != null) {
    chrome.sidePanel.open({ tabId: lastActiveTabId }).catch((err) => {
      console.warn('[BG] Side panel open failed:', err);
      showNotification('Vocify', 'Click the extension icon to open.');
    });
    return;
  }

  showNotification('Vocify', 'Focus a tab and try again.');
}


function clearCallWatch() {
  if (callWatchTimerId != null) {
    clearTimeout(callWatchTimerId);
    callWatchTimerId = null;
  }
  callWatchingRecordId = null;
  callWatchingRecordType = null;
}

function clearMemoPoll() {
  if (memoPollTimerId != null) {
    clearInterval(memoPollTimerId);
    memoPollTimerId = null;
  }
}

/**
 * Refresh HubSpot recordings for the record in the address bar.
 * Does not change status, start capture, or open a memo — the list is the UI.
 */
function startCallWatch(recordId, recordType) {
  if (!recordId) return;
  if (callWatchingRecordId === recordId && callWatchTimerId != null) return;
  clearCallWatch();
  callWatchingRecordId = recordId;
  callWatchingRecordType = recordType || 'deal';

  const scheduleNext = (ms) => {
    callWatchTimerId = setTimeout(tick, ms);
  };

  async function tick() {
    callWatchTimerId = null;
    if (callWatchingRecordId !== recordId) return;
    fetchRecordingsIfNeeded(
      { objectType: callWatchingRecordType, recordId: callWatchingRecordId },
      { force: true }
    );
    scheduleNext(20000);
  }
  scheduleNext(0);
}

function showNotification(title, message) {
  chrome.notifications.create('', {
    type: 'basic',
    iconUrl: '/icons/icon48.png',
    title: title || 'Vocify',
    message: message || '',
    priority: 2
  });
}

// ============================================
// OFFSCREEN DOCUMENT
// ============================================
async function getOffscreenDocument({ recreate = false } = {}) {
  const contexts = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
  if (contexts.length > 0) {
    if (!recreate) return;
    await chrome.offscreen.closeDocument().catch(() => {});
  }

  await chrome.offscreen.createDocument({
    url: OFFSCREEN_DOCUMENT_PATH,
    reasons: tabCaptureOffscreenReasons(),
    justification: 'Microphone memos and live tab-audio copilot',
  });
}

// ============================================
// RECORDING CONTROLS
// ============================================
async function loadPageSessionContext(tab, user) {
  const context = tab?.url ? parseHubSpotUrl(tab.url) : null;
  let pageVocab = [];
  let enriched = context;
  if (context?.objectType === 'deal' && context?.recordId) {
    const dealCtx = await api.get(`/crm/hubspot/deals/${context.recordId}/context`);
    pageVocab = Array.isArray(dealCtx?.sessionVocab) ? dealCtx.sessionVocab : [];
    enriched = {
      ...context,
      dealName: dealCtx?.raw_extraction?.dealname || context.dealName,
      companyName: dealCtx?.companyName || null,
      companyId: dealCtx?.companyId || null,
      contactName: dealCtx?.contactName || null,
      contactEmail: dealCtx?.contactEmail || null,
      contactPhone: dealCtx?.contactPhone || null,
      contactId: dealCtx?.contactId || null,
      dealContacts: Array.isArray(dealCtx?.contacts) ? dealCtx.contacts : [],
    };
  } else if (context?.objectType === 'contact' && context?.recordId) {
    const contactCtx = await api.get(`/crm/hubspot/contacts/${context.recordId}/context`);
    pageVocab = Array.isArray(contactCtx?.sessionVocab) ? contactCtx.sessionVocab : [];
    enriched = {
      ...context,
      contactName: contactCtx?.contactName || null,
      contactEmail: contactCtx?.contactEmail || null,
      contactPhone: contactCtx?.contactPhone || null,
      contactId: context.recordId,
      companyName: contactCtx?.companyName || null,
      companyId: contactCtx?.companyId || null,
    };
  } else if (context?.objectType === 'company' && context?.recordId) {
    const companyCtx = await api.get(`/crm/hubspot/companies/${context.recordId}/context`);
    pageVocab = Array.isArray(companyCtx?.sessionVocab) ? companyCtx.sessionVocab : [];
    enriched = {
      ...context,
      companyName: companyCtx?.companyName || null,
      companyId: context.recordId,
      contactId: companyCtx?.contactId || null,
      contactName: companyCtx?.contactName || null,
      contactEmail: companyCtx?.contactEmail || null,
      contactPhone: companyCtx?.contactPhone || null,
      companyContacts: Array.isArray(companyCtx?.contacts) ? companyCtx.contacts : [],
    };
  }
  return { vocab: mergeSessionVocab(pageVocab, user), enriched, context };
}

async function startRecording() {
  if (state.isRecording) return;
  if (state.call?.state && state.call.state !== CALL_STATES.IDLE) {
    showNotification('Vocify Copilot', 'Hang up the call before recording a memo.');
    return;
  }
  if (state.isCopilotListening) {
    showNotification('Vocify Copilot', 'Stop listening to the tab before recording a memo.');
    return;
  }
  clearCallWatch();
  
  try {
    const tab = await getContextTab();
    rememberTab(tab);
    const context = tab?.url ? parseHubSpotUrl(tab.url) : null;

    // Build WebSocket URL with user_id for glossary (same pattern as dashboard useRealtimeTranscription)
    const apiBase = await api.getApiBase();
    const wsBase = apiBaseToWsOrigin(apiBase);
    const user = await api.getCurrentUser().catch(() => null);
    const userId = user?.id || '';
    const wsUrl = new URL(`${wsBase}/api/v1/transcription/live`);
    wsUrl.searchParams.set('language', 'multi');
    if (userId) wsUrl.searchParams.set('user_id', userId);

    // Inject page-context names into STT vocab (contact / company / deal + caller)
    let enrichedContext = context;
    try {
      const { vocab, enriched } = await loadPageSessionContext(tab, user);
      enrichedContext = enriched || context;
      if (vocab.length) wsUrl.searchParams.set('session_vocab', vocab.join('|'));
    } catch (e) {
      console.warn('[BG] Failed to load page context for vocab:', e);
    }

    await getOffscreenDocument();
    chrome.runtime.sendMessage({ target: 'offscreen', type: 'START_RECORDING', wsUrl: wsUrl.toString() });
    
    updateState({ 
      isRecording: true, 
      status: 'recording', 
      finalTranscript: '',
      interimTranscript: '',
      context: enrichedContext,
      syncResult: null,
      currentMemoId: null
    });

    // UI already opened by command handler; no need to open again
  } catch (error) {
    console.error('[BG] Start recording error:', error);
    showNotification('Error', 'Mic permission required.');
    updateState({ isRecording: false, status: 'idle' });
  }
}

async function stopRecording() {
  if (!state.isRecording) return;
  
  chrome.runtime.sendMessage({ target: 'offscreen', type: 'STOP_RECORDING' });
  updateState({ isRecording: false, status: 'processing' });
  
  // Close offscreen document after a delay
  setTimeout(() => {
    chrome.offscreen.closeDocument().catch(() => {});
  }, 2000);
}

async function handleToggleRecording() {
  if (state.isCopilotListening) {
    showNotification('Vocify Copilot', 'Stop listening to the tab before recording a memo.');
    return;
  }
  if (state.isRecording) {
    await stopRecording();
  } else {
    const { accessToken } = await api.getTokens();
    if (!accessToken) {
      showNotification('Login Required', 'Log in above to start recording.');
      return;
    }
    await startRecording();
  }
}

let cachedCopilotUserId = '';
let cachedSessionVocab = [];

async function buildFastCopilotWsUrl() {
  const apiBase = await api.getApiBase();
  const wsBase = apiBaseToWsOrigin(apiBase);
  const wsUrl = new URL(`${wsBase}/api/v1/transcription/live`);
  wsUrl.searchParams.set('language', 'multi');
  wsUrl.searchParams.set('mode', COPILOT_CHANNEL_MODE);
  wsUrl.searchParams.set('channel_labels', 'prospect,rep');
  if (cachedCopilotUserId) wsUrl.searchParams.set('user_id', cachedCopilotUserId);
  if (cachedSessionVocab.length) {
    wsUrl.searchParams.set('session_vocab', cachedSessionVocab.join('|'));
  }
  return wsUrl;
}

function prefetchCopilotWsBits(tab) {
  api.getTokens()
    .then(({ accessToken }) => {
      if (!accessToken) return null;
      return api.getCurrentUser();
    })
    .then((user) => {
      if (!user) return null;
      cachedCopilotUserId = user.id || '';
      return loadPageSessionContext(tab, user);
    })
    .then((result) => {
      if (Array.isArray(result?.vocab)) cachedSessionVocab = result.vocab;
    })
    .catch(() => {});
}

async function getCaptureTab(requestedTabId) {
  if (requestedTabId != null) {
    try {
      return await chrome.tabs.get(requestedTabId);
    } catch (_) { /* fall through */ }
  }
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (tab?.id) return tab;
  } catch (_) { /* fall through */ }
  if (lastActiveTabId != null) {
    try {
      return await chrome.tabs.get(lastActiveTabId);
    } catch (_) { /* fall through */ }
  }
  return null;
}

function emptyCopilotUi() {
  return {
    copilotSuggestion: null,
    copilotRawStream: '',
    copilotIsLoading: false,
    copilotLastTurn: null,
    copilotError: null,
    copilotLatencyMs: null,
    copilotTabTitle: null,
  };
}

let copilotAbort = null;

function abortCopilotSuggest() {
  copilotAbort?.abort();
  copilotAbort = null;
}

async function requestCopilotSuggestion(latestTurn, transcriptWindow, speakerRole = 'prospect') {
  abortCopilotSuggest();
  const controller = new AbortController();
  copilotAbort = controller;
  updateState({
    copilotIsLoading: true,
    copilotRawStream: '',
    copilotSuggestion: null,
    copilotLastTurn: latestTurn,
    copilotError: null,
    copilotLatencyMs: null,
  });

  const stored = await chrome.storage.local.get([PRODUCT_CONTEXT_STORAGE_KEY]);
  const productContext = stored[PRODUCT_CONTEXT_STORAGE_KEY] || DEFAULT_PRODUCT_CONTEXT;

  try {
    await api.streamCopilotSuggest(
      {
        transcript_window: String(transcriptWindow || '').slice(-6000),
        latest_turn: latestTurn,
        product_context: productContext,
        language: 'auto',
        call_mode: 'meeting',
        speaker_role:
          speakerRole === 'rep' || speakerRole === 'unknown' ? speakerRole : 'prospect',
      },
      (event) => {
        if (controller.signal.aborted) return;
        if (event.type === 'token') {
          updateState({ copilotRawStream: `${state.copilotRawStream || ''}${event.text}` });
        } else if (event.type === 'result') {
          updateState({
            copilotSuggestion: event.suggestion,
            copilotIsLoading: false,
            copilotLatencyMs: event.latency_ms ?? null,
          });
        } else if (event.type === 'error') {
          updateState({ copilotError: event.message, copilotIsLoading: false });
        } else if (event.type === 'done') {
          updateState({ copilotIsLoading: false });
        }
      },
      controller.signal
    );
  } catch (err) {
    if (err?.name === 'AbortError') return;
    updateState({
      copilotError: err instanceof Error ? err.message : 'Suggestion failed',
      copilotIsLoading: false,
    });
  }
}

const copilotDetector = new TurnDetector({
  settleMs: 900,
  minWords: 6,
  speakerRole: 'prospect',
  setTimer: (fn, ms) => setTimeout(fn, ms),
  clearTimer: (id) => clearTimeout(id),
  onTurn: (turn, _full, meta) => {
    requestCopilotSuggestion(turn, state.finalTranscript, meta?.speakerRole || 'prospect');
  },
});

let listenStartTimerId = null;
/** Bumped on each Listen start and Stop so a late offscreen start cannot revive the session. */
let listenEpoch = 0;
/** Popup click generation — a Stop click invalidates an in-flight Start. */
let listenCommandSeq = 0;

function acceptListenCommandSeq(commandSeq) {
  if (commandSeq == null || !Number.isFinite(Number(commandSeq))) return true;
  const seq = Number(commandSeq);
  if (seq < listenCommandSeq) return false;
  listenCommandSeq = seq;
  return true;
}

function clearListenStartTimeout() {
  if (listenStartTimerId != null) {
    clearTimeout(listenStartTimerId);
    listenStartTimerId = null;
  }
}

function armListenStartTimeout() {
  clearListenStartTimeout();
  listenStartTimerId = setTimeout(() => {
    listenStartTimerId = null;
    if (state.listenPhase === 'starting') {
      failListen('stream_expired');
    }
  }, 8000);
}

function failListen(reason) {
  clearListenStartTimeout();
  copilotDetector.setEnabled(false);
  copilotDetector.reset();
  abortCopilotSuggest();
  listenEpoch += 1;
  chrome.runtime.sendMessage({
    target: 'offscreen',
    type: 'STOP_TAB_CAPTURE',
    minEpoch: listenEpoch,
  });
  chrome.offscreen.closeDocument().catch(() => {});
  const message = startDeniedMessage(reason);
  updateState({
    isCopilotListening: false,
    status: 'idle',
    listenPhase: 'error',
    ...emptyCopilotUi(),
    copilotError: message,
  });
  showNotification('Vocify Copilot', message);
  return { error: message, reason };
}

async function startTabCapture(requestedTabId, streamIdFromUi = null, commandSeq = null) {
  if (!acceptListenCommandSeq(commandSeq)) {
    return { ok: true, cancelled: true };
  }
  if (state.listenPhase === 'live' || state.isCopilotListening) {
    return { ok: true, alreadyLive: true };
  }
  if (state.listenPhase === 'starting') {
    return { ok: true, alreadyStarting: true };
  }

  const tabId = requestedTabId ?? lastActiveTabId;
  const tokenPromise = api.getTokens();
  const wsUrlPromise = buildFastCopilotWsUrl();

  const early = canStartTabCapture({
    isRecording: state.isRecording,
    isCopilotListening: state.isCopilotListening,
    hasToken: true,
    tabId: tabId ?? null,
    hasStreamId: Boolean(streamIdFromUi),
    callState: state.call?.state,
  });
  if (!early.ok) {
    if (early.reason === 'already_listening') return { ok: true, alreadyLive: true };
    return failListen(early.reason);
  }

  // Stream ids expire in a few seconds. Take the Listen-click id first;
  // otherwise request it here before tokens, HubSpot context, or tab lookup.
  let streamId = streamIdFromUi || null;
  if (!streamId) {
    streamId = await requestTabCaptureStreamId(chrome.tabCapture, tabId);
  }
  if (!streamId) {
    const tab = await getCaptureTab(tabId);
    const reason = listenFailureReason({ streamId: null, pageUrl: tab?.url });
    return failListen(reason);
  }

  const { accessToken } = await tokenPromise;
  const decision = canStartTabCapture({
    isRecording: state.isRecording,
    isCopilotListening: state.isCopilotListening,
    hasToken: Boolean(accessToken),
    tabId: tabId ?? null,
    hasStreamId: true,
    callState: state.call?.state,
  });
  if (!decision.ok) {
    if (decision.reason === 'already_listening') return { ok: true, alreadyLive: true };
    return failListen(decision.reason);
  }

  abortCopilotSuggest();
  copilotDetector.reset();

  await getOffscreenDocument({ recreate: false });
  const wsUrl = await wsUrlPromise;
  const epoch = ++listenEpoch;

  chrome.runtime.sendMessage({
    target: 'offscreen',
    type: 'START_TAB_CAPTURE',
    streamId,
    wsUrl: wsUrl.toString(),
    epoch,
  });

  const tab = await getCaptureTab(tabId);
  rememberTab(tab);
  prefetchCopilotWsBits(tab);
  const context = tab?.url ? parseHubSpotUrl(tab.url) : state.context;

  updateState({
    isCopilotListening: false,
    listenPhase: 'starting',
    status: 'copilot',
    finalTranscript: '',
    interimTranscript: '',
    prospectFinal: '',
    prospectInterim: '',
    finalWords: [],
    context,
    ...emptyCopilotUi(),
    copilotTabTitle: tab?.title || 'This tab',
    copilotError: null,
  });
  armListenStartTimeout();

  return { ok: true };
}

async function stopTabCapture(commandSeq = null) {
  acceptListenCommandSeq(commandSeq);
  listenEpoch += 1;
  clearListenStartTimeout();
  copilotDetector.setEnabled(false);
  copilotDetector.reset();
  abortCopilotSuggest();
  chrome.runtime.sendMessage({
    target: 'offscreen',
    type: 'STOP_TAB_CAPTURE',
    minEpoch: listenEpoch,
  });
  updateState({
    isCopilotListening: false,
    listenPhase: 'idle',
    status: 'idle',
    finalTranscript: '',
    interimTranscript: '',
    prospectFinal: '',
    prospectInterim: '',
    finalWords: [],
    ...emptyCopilotUi(),
  });
  chrome.offscreen.closeDocument().catch(() => {});
  return { ok: true };
}

// ============================================
// DATA PROCESSING
// ============================================
async function processAudioData(audioData) {
  try {
    console.log('[BG] Processing audio data...');
    const response = await fetch(audioData);
    const blob = await response.blob();

    // Pass the final transcript for faster processing
    const transcript = state.finalTranscript || null;
    console.log('[BG] Uploading memo, transcript length:', transcript?.length || 0);
    
    const result = await api.uploadMemo(blob, transcript);
    console.log('[BG] Upload result:', result);

    if (result.status === 'pending_review') {
      openReviewFromMemo(result.id, result);
      showNotification('Ready for Review', 'Review and sync CRM fields.');
      return;
    }
    updateState({ currentMemoId: result.id, status: 'processing' });
    showNotification('Processing', 'Extracting CRM fields…');
    startPolling(result.id);
  } catch (error) {
    console.error('[BG] Upload error:', error);
    updateState({ status: 'idle', currentMemoId: null });
    showNotification('Upload Failed', error.message);
  }
}

async function autoConfirmLegacyTranscript(memoId) {
  try {
    await api.post(`/memos/${memoId}/confirm-transcript`, {});
  } catch (err) {
    const detail = String(err?.data?.detail || err?.message || '');
    if (/Status:\s*(extracting|pending_review)/i.test(detail)) return;
    console.warn('[BG] Legacy confirm-transcript failed:', err);
  }
}

function startPolling(memoId) {
  clearMemoPoll();
  let pollCount = 0;
  console.log('[BG] Starting polling for memo:', memoId);

  const tick = async () => {
    pollCount += 1;
    try {
      const memo = await api.getMemo(memoId);
      console.log('[BG] Poll #', pollCount, 'status:', memo.status);

      if (memo.status === 'pending_transcript') {
        await autoConfirmLegacyTranscript(memoId);
        return;
      }
      if (memo.status === 'pending_review') {
        clearMemoPoll();
        showNotification('Ready for Review', 'Review and sync CRM fields.');
        openReviewFromMemo(memoId, memo);
      } else if (memo.status === 'approved') {
        clearMemoPoll();
        updateState({ status: 'success', syncResult: memo });
      } else if (memo.status === 'failed') {
        clearMemoPoll();
        updateState({ status: 'idle', currentMemoId: null, processingSource: null });
        showNotification('Couldn’t finish this call', memo.errorMessage || 'Try Transcribe again.');
      } else if (pollCount > 60) {
        clearMemoPoll();
        updateState({ status: 'idle', currentMemoId: null, processingSource: null });
        showNotification('Still working', 'This is taking longer than usual. Try again from the call list.');
      }
    } catch (e) {
      console.error('[BG] Polling error:', e);
      if (pollCount > 60) {
        clearMemoPoll();
        updateState({ status: 'idle', currentMemoId: null, processingSource: null });
        showNotification('Still working', 'This is taking longer than usual. Try again from the call list.');
      }
    }
  };
  tick();
  memoPollTimerId = setInterval(tick, 2000);
}

// ============================================
// OUTBOUND CALLING
// ============================================
function idleCall(error = null) {
  return {
    state: CALL_STATES.IDLE,
    to: null,
    callerId: null,
    error: error || null,
    callSid: null,
    answeredAt: null,
    muted: false,
    contactId: null,
    dealId: null,
  };
}

let callStatusPollId = null;
const CALL_STATUS_POLL_MS = 3000;
const CALL_STATUS_POLL_MAX_MS = 4 * 60 * 1000;

function clearCallStatusPoll() {
  if (callStatusPollId != null) {
    clearInterval(callStatusPollId);
    callStatusPollId = null;
  }
}

function startCallStatusPoll(callSid) {
  clearCallStatusPoll();
  if (!callSid) return;
  const startedAt = Date.now();
  const tick = async () => {
    if (Date.now() - startedAt > CALL_STATUS_POLL_MAX_MS) {
      clearCallStatusPoll();
      if (state.lastCall) {
        updateState({ lastCall: { ...state.lastCall, processing: false } });
      }
      return;
    }
    try {
      const call = await api.getCall(callSid);
      const terminal = call.status === 'logged' || call.status === 'failed';
      updateState({
        lastCall: {
          ...state.lastCall,
          memoId: call.memoId || null,
          memoStatus: call.memoStatus || null,
          processing: !terminal,
          errorMessage: call.errorMessage || null,
          durationSeconds: call.durationSeconds ?? state.lastCall?.durationSeconds,
        },
      });
      if (terminal) clearCallStatusPoll();
    } catch (_) { /* 404 until the webhook inserts; keep polling */ }
  };
  tick();
  callStatusPollId = setInterval(tick, CALL_STATUS_POLL_MS);
}

function snapshotLastCall(prev) {
  const answered = Boolean(prev.answeredAt);
  const endedAt = Date.now();
  const lastCall = {
    callSid: prev.callSid || null,
    to: prev.to,
    callerId: prev.callerId,
    contactId: prev.contactId,
    dealId: prev.dealId,
    answeredAt: prev.answeredAt || null,
    endedAt,
    durationMs: answered ? endedAt - prev.answeredAt : 0,
    memoId: null,
    memoStatus: null,
    processing: answered,
    outcome: answered ? 'answered' : 'no_answer',
    errorMessage: prev.error || null,
  };
  updateState({ call: idleCall(prev.error), lastCall });
  if (answered && lastCall.callSid) startCallStatusPoll(lastCall.callSid);
}

function isTabCapturing() {
  return (
    state.isCopilotListening ||
    state.listenPhase === 'starting' ||
    state.listenPhase === 'live'
  );
}

async function startCallFlow({ to, callerId }) {
  const gate = canStartCall({
    isRecording: state.isRecording,
    isTabCapturing: isTabCapturing(),
    callState: state.call.state,
  });
  if (!gate.ok) return { ok: false, error: gate.reason };

  const target = normalizeDialTarget(to);
  if (!target) return { ok: false, error: 'Número de teléfono no válido.' };

  let token;
  try {
    ({ token } = await api.createVoiceToken());
  } catch (e) {
    return { ok: false, error: 'No se pudo obtener el token de llamada.' };
  }

  await getOffscreenDocument();
  const context = state.context || {};
  const contactId = context.contactId || null;
  const dealId = context.objectType === 'deal' ? context.recordId : null;
  clearCallStatusPoll();
  chrome.runtime.sendMessage({
    target: 'offscreen',
    type: 'START_CALL',
    token,
    to: target,
    callerId,
    contactId,
    dealId,
  });

  updateState({
    lastCall: null,
    call: {
      state: CALL_STATES.CONNECTING,
      to: target,
      callerId,
      error: null,
      callSid: null,
      answeredAt: null,
      muted: false,
      contactId,
      dealId,
    },
  });
  return { ok: true, to: target };
}

function hangupCallFlow() {
  chrome.runtime.sendMessage({ target: 'offscreen', type: 'HANGUP_CALL' });
  updateState({ call: { ...state.call, state: CALL_STATES.ENDING } });
  return { ok: true };
}

// ============================================
// MESSAGE HANDLERS
// ============================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.target === 'offscreen') return;

  switch (message.type) {
    // State queries
    case 'GET_STATE': {
      (async () => {
        const { accessToken } = await api.getTokens().catch(() => ({ accessToken: null }));
        const payload = () => ({ ...state, authenticated: Boolean(accessToken) });
        if (!accessToken) {
          sendResponse(payload());
          return;
        }
        const flowBusy =
          state.isRecording ||
          state.isCopilotListening ||
          state.status === 'copilot';
        if (!flowBusy) {
          try {
            await refreshContextFromActiveTab();
          } catch (_) { /* keep last state */ }
        }
        sendResponse(payload());
      })();
      return true;
    }

    case 'LOGOUT':
      cachedCopilotUserId = '';
      cachedSessionVocab = [];
      recordingsKey = null;
      recordingsInFlightKey = null;
      recordingsFetchGen += 1;
      updateState({
        recordings: [],
        recordingsLoading: false,
        recordingsError: null,
      });
      break;
    
    case 'SET_STATE': {
      const newState = { ...message.state };
      // When opening a memo for review, refresh context from active HubSpot tab
      if (newState.status === 'review' && newState.currentMemoId) {
        getContextTab().then((tab) => {
          rememberTab(tab);
          const ctx = tab?.url ? parseHubSpotUrl(tab.url) : null;
          newState.context = planPageContextUpdate(state.context, ctx).context;
          updateState(newState);
        }).catch(() => updateState(newState));
      } else {
        updateState(newState);
        if (newState.status === 'processing' && newState.currentMemoId) {
          startPolling(String(newState.currentMemoId));
        }
      }
      break;
    }
    
    // Recording
    case 'TOGGLE_RECORDING':
      handleToggleRecording();
      break;

    case 'START_TAB_CAPTURE':
      startTabCapture(message.tabId, message.streamId, message.commandSeq)
        .then(sendResponse)
        .catch((e) => sendResponse({ error: e.message }));
      return true;

    case 'STOP_TAB_CAPTURE':
      stopTabCapture(message.commandSeq)
        .then(sendResponse)
        .catch((e) => sendResponse({ error: e.message }));
      return true;

    case 'RECORDING_STARTED':
      updateState({ isRecording: true, status: 'recording' });
      break;

    case 'RECORDING_COMPLETE':
      processAudioData(message.audioData);
      break;

    case 'RECORDING_ERROR':
      updateState({ isRecording: false, status: 'idle' });
      if (message.openSetup) {
        chrome.tabs.create({ url: chrome.runtime.getURL('setup.html') });
        showNotification('Microphone access', 'Allow the microphone on the Vocify page, then record again.');
      } else {
        showNotification('Recording Error', message.error);
      }
      break;

    case 'TAB_CAPTURE_STARTED':
      if (Number(message.epoch) !== listenEpoch || !shouldApplyTabCaptureLifecycle(state)) {
        chrome.runtime.sendMessage({
          target: 'offscreen',
          type: 'STOP_TAB_CAPTURE',
          minEpoch: listenEpoch,
        });
        chrome.offscreen.closeDocument().catch(() => {});
        break;
      }
      clearListenStartTimeout();
      copilotDetector.setEnabled(true);
      updateState({ isCopilotListening: true, listenPhase: 'live', status: 'copilot' });
      break;

    case 'TAB_CAPTURE_STOPPED':
      if (state.isCopilotListening || state.listenPhase === 'starting' || state.listenPhase === 'live') {
        clearListenStartTimeout();
        copilotDetector.setEnabled(false);
        abortCopilotSuggest();
        updateState({
          isCopilotListening: false,
          listenPhase: 'idle',
          status: 'idle',
          ...emptyCopilotUi(),
        });
      }
      break;

    case 'TAB_CAPTURE_ERROR':
      if (!shouldApplyTabCaptureLifecycle(state)) break;
      if (message.epoch != null && !isListenEpochCurrent(message.epoch, listenEpoch)) break;
      failListen(listenReasonFromOffscreenError(message.error));
      break;

    // Real-time transcript from offscreen
    case 'TRANSCRIPT_UPDATE': {
      const next = applyTranscriptUpdate(state, {
        text: message.text,
        isFinal: message.isFinal,
        words: message.words,
        audioChannel: message.audioChannel,
      });
      updateState(next);
      if (state.isCopilotListening) {
        copilotDetector.onFinalTranscript(next.prospectFinal);
        copilotDetector.onInterim(next.prospectInterim);
      }
      break;
    }

    case 'END_OF_UTTERANCE':
      if (state.isCopilotListening && isCoachableChannel(message.audioChannel)) {
        copilotDetector.onEndOfUtterance();
      }
      break;

    case 'CALL_STATE': {
      const prev = state.call || idleCall();
      const nextState = message.state;
      if (nextState === CALL_STATES.IDLE && prev.state !== CALL_STATES.IDLE) {
        snapshotLastCall({
          ...prev,
          error: message.error || prev.error,
          callSid: message.callSid || prev.callSid,
        });
        break;
      }
      updateState({
        call: {
          ...prev,
          state: nextState,
          error: message.error || null,
          to: nextState === CALL_STATES.IDLE ? null : prev.to,
          callSid: message.callSid || prev.callSid,
          answeredAt: message.answeredAt || prev.answeredAt,
          muted: message.muted != null ? Boolean(message.muted) : prev.muted,
        },
      });
      break;
    }

    case 'START_CALL':
      startCallFlow(message).then(sendResponse);
      return true;

    case 'HANGUP_CALL':
      sendResponse(hangupCallFlow());
      return true;

    case 'MUTE_CALL':
      chrome.runtime.sendMessage({
        target: 'offscreen',
        type: 'MUTE_CALL',
        muted: Boolean(message.muted),
      });
      sendResponse({ ok: true });
      break;

    case 'SEND_DIGITS':
      chrome.runtime.sendMessage({
        target: 'offscreen',
        type: 'SEND_DIGITS',
        digits: message.digits,
      });
      sendResponse({ ok: true });
      break;

    case 'CALL_TOKEN_REFRESH_REQUEST':
      api.createVoiceToken()
        .then(({ token }) => {
          chrome.runtime.sendMessage({ target: 'offscreen', type: 'UPDATE_TOKEN', token });
        })
        .catch(() => {});
      break;

    case 'DISMISS_LAST_CALL':
      clearCallStatusPoll();
      updateState({ lastCall: null });
      sendResponse({ ok: true });
      break;

    case 'OPEN_CALL_MEMO': {
      const memoId = message.memoId;
      if (!memoId) {
        sendResponse({ ok: false });
        break;
      }
      api.getMemo(memoId)
        .then((memo) => {
          openReviewFromMemo(memoId, memo);
          sendResponse({ ok: true });
        })
        .catch((e) => sendResponse({ ok: false, error: e.message }));
      return true;
    }

    case 'GET_CALLING_CONFIG':
      api.getCallingConfig().then(sendResponse).catch(() =>
        sendResponse({ enabled: false, callerIds: [] })
      );
      return true;

    case 'VERIFY_CALLER_ID':
      api
        .verifyCallerId(message.phoneNumber, message.label)
        .then((r) => sendResponse({ ok: true, ...r }))
        .catch((e) => sendResponse({ ok: false, error: e.message }));
      return true;

    // API Proxies (for popup)
    case 'SEARCH_DEALS':
      console.log('[BG] Searching deals for query:', message.query);
      api.get(`/crm/hubspot/search/deals?q=${encodeURIComponent(message.query)}`)
        .then(results => {
          console.log('[BG] Search results from API:', results?.length || 0);
          sendResponse(results);
        })
        .catch(e => {
          console.error('[BG] Search API error:', e);
          sendResponse({ error: e.message });
        });
      return true; // Keep channel open for async response

    case 'SEARCH_CONTACTS':
      api.get(`/crm/hubspot/search/contacts?q=${encodeURIComponent(message.query || '')}`)
        .then((results) => sendResponse(results))
        .catch((e) => sendResponse({ error: (e && e.data && e.data.detail) || e.message }));
      return true;

    case 'GET_CALL_HISTORY':
      api.getCallHistory({
        limit: message.limit || 20,
        contactId: message.contactId || undefined,
        dealId: message.dealId || undefined,
      })
        .then(sendResponse)
        .catch((e) => sendResponse({ error: e.message }));
      return true;

    case 'GET_PREVIEW':
      requestMemoPreview({
        memoId: message.memoId,
        dealId: message.dealId || null,
        contactId: message.contactId || null,
        createNewDeal: !!message.createNewDeal,
        extraction: message.extraction || null,
      })
        .then(sendResponse)
        .catch((e) => sendResponse({ error: e.message }));
      return true;

    case 'APPROVE_SYNC':
      api.post(`/memos/${message.memoId}/approve`, { 
        deal_id: message.dealId,
        is_new_deal: message.isNewDeal,
        extraction: message.extraction || undefined,
        contact_id: message.contactId || undefined,
        company_id: message.companyId || undefined,
        skip_deal: !!message.skipDeal,
        create_note: message.createNote !== false,
      })
        .then(result => {
          updateState({ status: 'success', syncResult: result });
          sendResponse({ success: true, result });
        })
        .catch(e => sendResponse({
          // e.data is the parsed JSON body ({ detail, error_code }) the backend
          // sends on failure; e.message defaults to a generic "API Error: <status>"
          // that hides the real reason (e.g. "select a deal for Salesforce").
          error: (e && e.data && e.data.detail) || e.message,
          errorCode: (e && e.data && e.data.error_code) || null,
        }));
      return true;

    case 'GET_DEAL_CONTEXT':
      api.get(`/crm/hubspot/deals/${message.dealId}/context`)
        .then(sendResponse)
        .catch(e => sendResponse({ error: e.message }));
      return true;

    case 'GET_CONTACT_CONTEXT':
      api.get(`/crm/hubspot/contacts/${message.contactId}/context`)
        .then(sendResponse)
        .catch(e => sendResponse({ error: e.message }));
      return true;

    case 'GET_COMPANY_CONTEXT':
      api.get(`/crm/hubspot/companies/${message.companyId}/context`)
        .then(sendResponse)
        .catch(e => sendResponse({ error: e.message }));
      return true;

    case 'GET_CRM_CONFIG':
      api.get('/crm/hubspot/configuration')
        .then(sendResponse)
        .catch(e => sendResponse({ error: e.message }));
      return true;

    case 'GET_RECENT_MEMOS': {
      const params = new URLSearchParams();
      if (message.dealId) params.set('hubspot_deal_id', String(message.dealId));
      else if (message.contactId) params.set('hubspot_contact_id', String(message.contactId));
      params.set('limit', '5');
      api.get(`/memos?${params.toString()}`)
        .then((results) => sendResponse(memoListFromResponse(results)))
        .catch((e) => {
          if (isAuthFailure(e)) {
            chrome.runtime.sendMessage({ type: 'AUTH_REQUIRED' }).catch(() => {});
          }
          sendResponse({ error: e.message });
        });
      return true;
    }

    case 'PROCESS_HUBSPOT_CALL': {
      const callId = message.callId;
      if (!callId) {
        sendResponse({ error: 'Missing callId' });
        break;
      }
      clearCallWatch();
      updateState({
        status: 'processing',
        processingSource: 'hubspot_call',
      });
      api.post(`/crm/hubspot/calls/${encodeURIComponent(callId)}/process`, {})
        .then((res) => {
          const memoId = res?.memo_id ? String(res.memo_id) : null;
          const st = res?.status;
          if (memoId && (st === 'transcribing' || st === 'uploading' || st === 'extracting')) {
            updateState({
              status: 'processing',
              currentMemoId: memoId,
              processingSource: 'hubspot_call',
            });
            startPolling(memoId);
          } else if (memoId && st === 'pending_review') {
            api.getMemo(memoId)
              .then((memo) => {
                openReviewFromMemo(memoId, memo);
                updateState({ processingSource: 'hubspot_call' });
              })
              .catch(() => {
                updateState({ status: 'review', currentMemoId: memoId });
              });
          } else if (memoId && st === 'pending_transcript') {
            updateState({
              status: 'processing',
              currentMemoId: memoId,
              processingSource: 'hubspot_call',
            });
            startPolling(memoId);
          } else if (memoId && st === 'failed') {
            updateState({ status: 'idle', currentMemoId: null, processingSource: null });
          }
          if (state.context) fetchRecordingsIfNeeded(state.context, { force: true });
          sendResponse(res);
        })
        .catch((e) => {
          updateState({ status: 'idle', processingSource: null });
          sendResponse({ error: e.message });
        });
      return true;
    }

    case 'STOP_CALL_WATCH':
      clearCallWatch();
      sendResponse({ ok: true });
      break;

    case 'DISCARD_MEMO':
      // Remember this memo so restarting the contact/deal watcher does not reopen it
      if (state.currentMemoId) ignoredCallMemoIds.add(String(state.currentMemoId));
      clearMemoPoll();
      clearCallWatch();
      updateState({ 
        status: 'idle', 
        currentMemoId: null, 
        syncResult: null,
        context: null,
        recordings: [],
        recordingsLoading: true,
        recordingsError: null,
        finalTranscript: '',
        interimTranscript: '',
        processingSource: null,
      });
      recordingsKey = null;
      recordingsInFlightKey = null;
      recordingsFetchGen += 1;
      refreshContextFromActiveTab().catch(() => {});
      break;
  }
});

// ============================================
// SIDE PANEL: Make icon click open side panel
// ============================================
if (chrome.sidePanel?.setPanelBehavior) {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
}

// ============================================
// PRE-FETCH TAB: sidePanel.open must run sync in user gesture (~1ms)
// ============================================
function seedActiveTab() {
  getContextTab().then((tab) => rememberTab(tab)).catch(() => {});
}

// ============================================
// TAB CONTEXT TRACKING
// Re-evaluates the deal/contact watcher whenever the user navigates or switches tabs.
// HubSpot is an SPA — URL often changes without a full load, so we must listen to
// changeInfo.url as well as status===complete.
// ============================================

/**
 * Fetch display names for the HubSpot record in the address bar.
 * Keeps objectType/recordId from the URL; fills contactName / dealName / companyName.
 */
async function enrichPageContext(ctx) {
  if (!ctx?.recordId || !ctx.objectType) return ctx;
  const key = `${ctx.objectType}:${ctx.recordId}`;
  try {
    const { accessToken } = await api.getTokens();
    if (!accessToken) return ctx;

    if (ctx.objectType === 'contact') {
      const contactCtx = await api.get(`/crm/hubspot/contacts/${ctx.recordId}/context`);
      return {
        ...ctx,
        contactName: contactCtx?.contactName || ctx.contactName || null,
        contactEmail: contactCtx?.contactEmail || null,
        contactPhone: contactCtx?.contactPhone || null,
        contactId: ctx.recordId,
        companyName: contactCtx?.companyName || null,
        companyId: contactCtx?.companyId || null,
        _enrichedKey: key,
      };
    }
    if (ctx.objectType === 'deal') {
      const dealCtx = await api.get(`/crm/hubspot/deals/${ctx.recordId}/context`);
      return {
        ...ctx,
        dealName: dealCtx?.raw_extraction?.dealname || ctx.dealName || null,
        companyName: dealCtx?.companyName || null,
        companyId: dealCtx?.companyId || null,
        contactId: dealCtx?.contactId || null,
        contactName: dealCtx?.contactName || null,
        contactEmail: dealCtx?.contactEmail || null,
        contactPhone: dealCtx?.contactPhone || null,
        dealContacts: Array.isArray(dealCtx?.contacts) ? dealCtx.contacts : [],
        _enrichedKey: key,
      };
    }
    if (ctx.objectType === 'company') {
      const companyCtx = await api.get(`/crm/hubspot/companies/${ctx.recordId}/context`);
      return {
        ...ctx,
        companyName: companyCtx?.companyName || ctx.companyName || null,
        companyId: ctx.recordId,
        contactId: companyCtx?.contactId || null,
        contactName: companyCtx?.contactName || null,
        contactEmail: companyCtx?.contactEmail || null,
        contactPhone: companyCtx?.contactPhone || null,
        companyContacts: Array.isArray(companyCtx?.contacts) ? companyCtx.contacts : [],
        _enrichedKey: key,
      };
    }
  } catch (e) {
    console.warn('[BG] Failed to enrich page context:', e);
  }
  return ctx;
}

function applyEnrichedIfCurrent(enriched) {
  if (recordScopeKey(state.context) !== recordScopeKey(enriched)) return;
  updateState({ context: enriched });
}

async function refreshContextFromActiveTab() {
  const tab = await getContextTab();
  rememberTab(tab);
  if (!tab?.id || !tab.url) {
    applyContextAsync(null);
    return;
  }
  lastSeenUrlByTab.set(tab.id, tab.url);
  reevaluateTabContextAuthenticated(tab.id, tab.url);
}

function applyContextAsync(ctx) {
  const plan = planPageContextUpdate(state.context, ctx);
  const { context, skipBroadcast, replaceLists } = plan;
  const key = recordScopeKey(context);

  if (skipBroadcast) {
    fetchRecordingsIfNeeded(context);
    if (key && context._enrichedKey !== key) {
      enrichPageContext(context).then(applyEnrichedIfCurrent);
    }
    return;
  }

  if (replaceLists) {
    recordingsKey = null;
    recordingsInFlightKey = null;
    recordingsFetchGen += 1;
  }
  updateState({
    context,
    recordings: replaceLists ? [] : (state.recordings || []),
    recordingsLoading: replaceLists ? true : state.recordingsLoading,
    recordingsError: replaceLists ? null : state.recordingsError,
    lastCall: replaceLists ? null : state.lastCall,
  });
  fetchRecordingsIfNeeded(context);
  if (!key) return;
  enrichPageContext(context).then(applyEnrichedIfCurrent);
}

function recordingsEndpoint(ctx) {
  if (ctx?.objectType === 'contact' && ctx.recordId) {
    return `/crm/hubspot/contacts/${ctx.recordId}/recordings`;
  }
  if (ctx?.objectType === 'deal' && ctx.recordId) {
    return `/crm/hubspot/deals/${ctx.recordId}/recordings`;
  }
  if (ctx?.objectType === 'company' && ctx.recordId) {
    return `/crm/hubspot/companies/${ctx.recordId}/recordings`;
  }
  return '/crm/hubspot/recordings?limit=20';
}

function fetchRecordingsIfNeeded(ctx, { force = false } = {}) {
  const endpoint = recordingsEndpoint(ctx);
  const key = recordingsScopeKey(ctx);
  const plan = planRecordingsFetch({
    scopeKey: key,
    cacheKey: recordingsKey,
    inFlightKey: recordingsInFlightKey,
    loading: state.recordingsLoading,
    force,
  });
  if (plan.action !== 'fetch') return;

  const keepList = recordingsKey === key;
  recordingsInFlightKey = key;
  const gen = ++recordingsFetchGen;
  updateState({
    recordingsLoading: true,
    recordings: keepList ? (state.recordings || []) : [],
    recordingsError: null,
  });

  const settleInFlight = () => {
    if (recordingsInFlightKey === key && gen === recordingsFetchGen) {
      recordingsInFlightKey = null;
    }
  };

  api.get(endpoint)
    .then((items) => {
      const action = planRecordingsResult({
        gen,
        fetchGen: recordingsFetchGen,
        resultScopeKey: key,
        currentScopeKey: recordingsScopeKey(state.context),
      }).action;
      if (action === 'ignore') return;
      settleInFlight();
      if (action === 'abandon') {
        updateState({ recordingsLoading: false });
        return;
      }
      recordingsKey = key;
      const list = Array.isArray(items)
        ? items.map((rec) => ({ ...rec, timestamp: rec.timestamp || rec.timestamp_ms || null }))
        : [];
      updateState({ recordings: list, recordingsLoading: false, recordingsError: null });
    })
    .catch((e) => {
      console.warn('[BG] Failed to load recordings:', e);
      const action = planRecordingsResult({
        gen,
        fetchGen: recordingsFetchGen,
        resultScopeKey: key,
        currentScopeKey: recordingsScopeKey(state.context),
      }).action;
      if (action === 'ignore') {
        if (isAuthFailure(e)) {
          chrome.runtime.sendMessage({ type: 'AUTH_REQUIRED' }).catch(() => {});
        }
        return;
      }
      settleInFlight();
      if (isAuthFailure(e)) {
        updateState({ recordingsLoading: false, recordings: [], recordingsError: null });
        chrome.runtime.sendMessage({ type: 'AUTH_REQUIRED' }).catch(() => {});
        return;
      }
      if (action === 'abandon') {
        updateState({ recordingsLoading: false });
        return;
      }
      recordingsKey = key;
      const reconnect = isCrmReconnectError(e)
        ? 'HubSpot login expired. Reconnect HubSpot in Vocify → Integrations, then try again.'
        : null;
      updateState({ recordings: [], recordingsLoading: false, recordingsError: reconnect });
    });
}

function reevaluateTabContext(tabId, url) {
  if (!url) return;
  lastSeenUrlByTab.set(tabId, url);
  api.getTokens().then(({ accessToken }) => {
    if (!accessToken) return;
    reevaluateTabContextAuthenticated(tabId, url);
  }).catch(() => {});
}

function reevaluateTabContextAuthenticated(tabId, url) {
  const ctx = parseHubSpotUrl(url);
  const activityTypes = ['deal', 'contact', 'company'];
  const recordType = ctx?.objectType;
  const recordId = activityTypes.includes(recordType) ? ctx.recordId : null;

  // Always refresh page context (even during review) so "use contact on this page" stays accurate.
  // Never start/stop watches or change status while a flow is active.
  const flowBusy =
    state.isRecording ||
    state.isCopilotListening ||
    state.status === 'copilot' ||
    state.status === 'processing' ||
    state.status === 'review' ||
    state.status === 'success';

  if (flowBusy) {
    applyContextAsync(ctx);
    return;
  }

  applyContextAsync(ctx);
  if (recordId) startCallWatch(recordId, recordType);
  else clearCallWatch();
}

chrome.tabs.onActivated.addListener(({ tabId }) => {
  lastActiveTabId = tabId;
  state = { ...state, captureTabId: tabId };
  chrome.tabs.get(tabId, (tab) => {
    if (chrome.runtime.lastError) {
      refreshContextFromActiveTab().catch(() => applyContextAsync(null));
      return;
    }
    if (tab?.url) reevaluateTabContext(tabId, tab.url);
  });
});

chrome.tabs.onRemoved.addListener((tabId) => {
  lastSeenUrlByTab.delete(tabId);
  if (tabId !== lastActiveTabId) return;
  lastActiveTabId = null;
  refreshContextFromActiveTab().catch(() => applyContextAsync(null));
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tabId !== lastActiveTabId) return;
  const url = changeInfo.url || tab?.url;
  if (!url) return;
  if (url !== lastSeenUrlByTab.get(tabId) || changeInfo.status === 'complete') {
    reevaluateTabContext(tabId, url);
  }
});

chrome.windows.onFocusChanged.addListener(() => seedActiveTab());
chrome.runtime.onStartup.addListener(seedActiveTab);
seedActiveTab();
api.getApiBase().then((base) => {
  console.log('[BG] API base:', base);
}).catch(() => {});
setInterval(() => {
  if (!lastActiveTabId) return;
  chrome.tabs.get(lastActiveTabId, (tab) => {
    if (chrome.runtime.lastError || !tab?.url) return;
    if (tab.url !== lastSeenUrlByTab.get(lastActiveTabId)) {
      reevaluateTabContext(lastActiveTabId, tab.url);
    }
  });
}, 400);
prefetchCopilotWsBits(null);

// ============================================
// HOTKEY COMMAND
// ============================================
chrome.commands.onCommand.addListener((command) => {
  const actions = actionsForCommand(command);
  if (actions.openUi) openExtensionUI();
  if (actions.toggleRecording) handleToggleRecording();
});
