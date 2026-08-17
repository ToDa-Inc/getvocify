/**
 * Service Worker for Vocify Chrome Extension
 * 
 * The "Brain" of the extension. Maintains state even when popup is closed.
 */

import { api } from './lib/api.js';
import { parseHubSpotUrl } from './lib/hubspot-parser.js';
import { panelOpenState } from './lib/call-watch.js';

const OFFSCREEN_DOCUMENT_PATH = 'offscreen.html';

// ============================================
// CENTRAL STATE (Source of Truth)
// ============================================
let state = {
  isRecording: false,
  finalTranscript: '',
  interimTranscript: '',
  currentMemoId: null,
  status: 'idle', // idle, recording, processing, review, success
  context: null,
  syncResult: null,
  watchingForRecording: false,
  processingSource: null, // 'hubspot_call' | null
  recordings: [],
  recordingsLoading: false,
};

/** Cached for sidePanel.open – must be called synchronously in user gesture, no await before it */
let lastActiveTabId = null;
/** Last deal/contact key we fetched HubSpot recordings for */
let recordingsKey = null;

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
    const hubspotTabs = await chrome.tabs.query({ url: ['https://*.hubspot.com/*'] });
    candidates.push(...hubspotTabs.filter((t) => t.active));
    candidates.push(...hubspotTabs.filter((t) => !t.active));
  } catch (_) { /* host permission may be missing */ }

  const seen = new Set();
  const unique = [];
  for (const tab of candidates) {
    if (!tab?.id || seen.has(tab.id)) continue;
    seen.add(tab.id);
    unique.push(tab);
  }

  const focused = unique[0];
  if (focused?.url && /hubspot\.com/i.test(focused.url)) {
    lastActiveTabId = focused.id;
    return focused;
  }

  const recordTab = unique.find((t) => t.url && parseHubSpotUrl(t.url)?.recordId);
  const chosen = recordTab || focused || unique[0] || null;
  if (chosen?.id != null) lastActiveTabId = chosen.id;
  return chosen;
}

function rememberTab(tab) {
  if (tab?.id != null) lastActiveTabId = tab.id;
}

let callWatchTimerId = null;
let callWatchingRecordId = null;  // deal or contact id being watched
let callWatchingRecordType = null; // 'deal' | 'contact'
/** Interval for user-initiated memo processing (mic upload or Transcribe). */
let memoPollTimerId = null;
/** Memos the user dismissed. Never auto-open these. */
const ignoredCallMemoIds = new Set();

// ============================================
// STATE MANAGEMENT
// ============================================
function updateState(newState) {
  state = { ...state, ...newState };
  
  // Update badge
  chrome.action.setBadgeText({ text: state.isRecording ? 'REC' : '' });
  if (state.isRecording) chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });
  
  // Broadcast to popup (if open)
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
  if (state.watchingForRecording) {
    updateState({ watchingForRecording: false });
  }
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
async function getOffscreenDocument() {
  const contexts = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
  if (contexts.length > 0) return;

  await chrome.offscreen.createDocument({
    url: OFFSCREEN_DOCUMENT_PATH,
    reasons: ['USER_MEDIA'],
    justification: 'Recording audio for voice memos',
  });
}

// ============================================
// RECORDING CONTROLS
// ============================================
async function startRecording() {
  if (state.isRecording) return;
  clearCallWatch();
  
  try {
    const tab = await getContextTab();
    rememberTab(tab);
    const context = tab?.url ? parseHubSpotUrl(tab.url) : null;

    // Build WebSocket URL with user_id for glossary (same pattern as dashboard useRealtimeTranscription)
    const apiBase = await api.getApiBase();
    const wsBase = apiBase.replace(/^http/, 'ws').replace(/\/api\/v1\/?$/, '');
    const user = await api.getCurrentUser().catch(() => null);
    const userId = user?.id || '';
    const wsUrl = new URL(`${wsBase}/api/v1/transcription/live`);
    wsUrl.searchParams.set('language', 'multi');
    if (userId) wsUrl.searchParams.set('user_id', userId);

    // Inject page-context names into STT vocab (contact / company / deal)
    let enrichedContext = context;
    try {
      if (context?.objectType === 'deal' && context?.recordId) {
        const dealCtx = await api.get(`/crm/hubspot/deals/${context.recordId}/context`);
        const vocab = Array.isArray(dealCtx?.sessionVocab) ? dealCtx.sessionVocab : [];
        if (vocab.length) wsUrl.searchParams.set('session_vocab', vocab.join('|'));
        enrichedContext = {
          ...context,
          dealName: dealCtx?.raw_extraction?.dealname || context.dealName,
          companyName: dealCtx?.companyName || null,
          companyId: dealCtx?.companyId || null,
          contactName: dealCtx?.contactName || null,
          contactEmail: dealCtx?.contactEmail || null,
          contactId: dealCtx?.contactId || null,
        };
      } else if (context?.objectType === 'contact' && context?.recordId) {
        const contactCtx = await api.get(`/crm/hubspot/contacts/${context.recordId}/context`);
        const vocab = Array.isArray(contactCtx?.sessionVocab) ? contactCtx.sessionVocab : [];
        if (vocab.length) wsUrl.searchParams.set('session_vocab', vocab.join('|'));
        enrichedContext = {
          ...context,
          contactName: contactCtx?.contactName || null,
          contactEmail: contactCtx?.contactEmail || null,
          contactId: context.recordId,
          companyName: contactCtx?.companyName || null,
          companyId: contactCtx?.companyId || null,
        };
      } else if (context?.objectType === 'company' && context?.recordId) {
        const companyCtx = await api.get(`/crm/hubspot/companies/${context.recordId}/context`);
        const vocab = Array.isArray(companyCtx?.sessionVocab) ? companyCtx.sessionVocab : [];
        if (vocab.length) wsUrl.searchParams.set('session_vocab', vocab.join('|'));
        enrichedContext = {
          ...context,
          companyName: companyCtx?.companyName || null,
          companyId: context.recordId,
          contactId: companyCtx?.contactId || null,
          contactName: companyCtx?.contactName || null,
          contactEmail: companyCtx?.contactEmail || null,
          companyContacts: Array.isArray(companyCtx?.contacts) ? companyCtx.contacts : [],
        };
      }
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

    // If transcript was sent, backend returns pending_transcript immediately - go straight to review
    if (result.status === 'pending_transcript' || result.status === 'pending_review') {
      updateState({ currentMemoId: result.id, status: 'review' });
      showNotification('Ready for Review', 'Review and confirm your transcript.');
      return;
    }
    updateState({ currentMemoId: result.id, status: 'processing' });
    showNotification('Transcribing', 'Converting speech to text...');
    startPolling(result.id);
  } catch (error) {
    console.error('[BG] Upload error:', error);
    updateState({ status: 'idle', currentMemoId: null });
    showNotification('Upload Failed', error.message);
  }
}

function startPolling(memoId) {
  clearMemoPoll();
  let pollCount = 0;
  console.log('[BG] Starting polling for memo:', memoId);

  memoPollTimerId = setInterval(async () => {
    pollCount += 1;
    try {
      const memo = await api.getMemo(memoId);
      console.log('[BG] Poll #', pollCount, 'status:', memo.status);

      if (memo.status === 'pending_review' || memo.status === 'pending_transcript') {
        clearMemoPoll();
        showNotification('Ready for Review', 'Review and confirm your transcript.');
        updateState({ status: 'review', currentMemoId: memoId });
      } else if (memo.status === 'approved') {
        clearMemoPoll();
        updateState({ status: 'success', syncResult: memo });
      } else if (memo.status === 'failed') {
        clearMemoPoll();
        updateState({ status: 'idle', currentMemoId: null, processingSource: null });
        showNotification('Analysis Failed', memo.errorMessage || 'Unknown error');
      } else if (pollCount > 60) {
        clearMemoPoll();
        updateState({ status: 'idle', currentMemoId: null, processingSource: null });
        showNotification('Timeout', 'Processing took too long.');
      }
    } catch (e) {
      console.error('[BG] Polling error:', e);
      if (pollCount > 60) {
        clearMemoPoll();
        updateState({ status: 'idle', currentMemoId: null, processingSource: null });
        showNotification('Timeout', 'Processing took too long.');
      }
    }
  }, 2000);
}

// ============================================
// MESSAGE HANDLERS
// ============================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.target === 'offscreen') return;

  switch (message.type) {
    // State queries
    case 'GET_STATE': {
      const opened = panelOpenState(state);
      if (opened !== state && opened.status === 'idle' && state.status === 'processing') {
        if (state.currentMemoId) ignoredCallMemoIds.add(String(state.currentMemoId));
        clearMemoPoll();
        updateState({
          status: 'idle',
          processingSource: null,
        });
      }
      if (state.status === 'review' && state.currentMemoId) {
        getContextTab().then((tab) => {
          rememberTab(tab);
          if (tab?.url) {
            const ctx = parseHubSpotUrl(tab.url);
            if (ctx?.recordId && ['deal', 'contact', 'company'].includes(ctx.objectType)) {
              applyContextAsync(ctx);
            }
          }
          sendResponse(state);
        }).catch(() => sendResponse(state));
        return true;
      }
      if (state.status === 'idle' && !state.isRecording) {
        getContextTab().then((tab) => {
          rememberTab(tab);
          if (tab?.url) reevaluateTabContext(tab.id, tab.url);
          else updateState({ context: null, recordings: [], recordingsLoading: false });
          sendResponse(state);
        }).catch(() => sendResponse(state));
        return true;
      }
      sendResponse(state);
      break;
    }
    
    case 'SET_STATE': {
      const newState = { ...message.state };
      // When opening a memo for review, refresh context from active HubSpot tab
      if (newState.status === 'review' && newState.currentMemoId) {
        getContextTab().then((tab) => {
          rememberTab(tab);
          if (tab?.url) {
            const ctx = parseHubSpotUrl(tab.url);
            if (ctx?.recordId && ['deal', 'contact', 'company'].includes(ctx.objectType)) {
              newState.context = ctx;
            }
          }
          updateState(newState);
        }).catch(() => updateState(newState));
      } else {
        updateState(newState);
      }
      break;
    }
    
    // Recording
    case 'TOGGLE_RECORDING':
      handleToggleRecording();
      break;

    case 'RECORDING_STARTED':
      updateState({ isRecording: true, status: 'recording' });
      break;

    case 'RECORDING_COMPLETE':
      processAudioData(message.audioData);
      break;

    case 'RECORDING_ERROR':
      updateState({ isRecording: false, status: 'idle' });
      showNotification('Recording Error', message.error);
      break;

    // Real-time transcript from offscreen
    case 'TRANSCRIPT_UPDATE':
      if (message.isFinal) {
        // Append to final transcript
        const newFinal = state.finalTranscript 
          ? `${state.finalTranscript} ${message.text}` 
          : message.text;
        updateState({ finalTranscript: newFinal, interimTranscript: '' });
      } else {
        // Update interim only
        updateState({ interimTranscript: message.text });
      }
      break;

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

    case 'GET_PREVIEW':
      if (message.extraction) {
        api.post(`/memos/${message.memoId}/preview`, { 
          deal_id: message.dealId || null,
          contact_id: message.contactId || null,
          create_new_deal: !!message.createNewDeal,
          extraction: message.extraction 
        })
          .then(sendResponse)
          .catch(e => sendResponse({ error: e.message }));
      } else {
        const params = new URLSearchParams();
        if (message.dealId) params.set('deal_id', message.dealId);
        if (message.contactId) params.set('contact_id', message.contactId);
        if (message.createNewDeal) params.set('create_new_deal', 'true');
        const qs = params.toString();
        const previewUrl = `/memos/${message.memoId}/preview${qs ? `?${qs}` : ''}`;
        api.get(previewUrl)
          .then(sendResponse)
          .catch(e => sendResponse({ error: e.message }));
      }
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
        // Optional - the popup only sends these when the rep actually picked
        // an outcome. lost_reason is validated server-side (422 if missing
        // for 'lost'), the popup's own gating is just UX, not the real check.
        call_outcome: message.callOutcome || undefined,
        lost_reason: message.lostReason || undefined,
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
        .then((results) => sendResponse(Array.isArray(results) ? results : []))
        .catch((e) => sendResponse({ error: e.message }));
      return true;
    }

    case 'PROCESS_HUBSPOT_CALL': {
      const callId = message.callId;
      if (!callId) {
        sendResponse({ error: 'Missing callId' });
        break;
      }
      api.post(`/crm/hubspot/calls/${encodeURIComponent(callId)}/process`, {})
        .then((res) => {
          const memoId = res?.memo_id ? String(res.memo_id) : null;
          const st = res?.status;
          if (memoId && (st === 'transcribing' || st === 'uploading' || st === 'extracting')) {
            clearCallWatch();
            updateState({
              status: 'processing',
              currentMemoId: memoId,
              watchingForRecording: false,
              processingSource: 'hubspot_call',
            });
            startPolling(memoId);
          } else if (memoId && (st === 'pending_transcript' || st === 'pending_review')) {
            clearCallWatch();
            updateState({ status: 'review', currentMemoId: memoId, watchingForRecording: false });
          }
          if (state.context) fetchRecordingsIfNeeded(state.context, { force: true });
          sendResponse(res);
        })
        .catch((e) => sendResponse({ error: e.message }));
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
        finalTranscript: '',
        interimTranscript: '',
        watchingForRecording: false,
        processingSource: null,
      });
      // Re-evaluate the current tab so the watcher restarts if still on a deal/contact page
      getContextTab().then((tab) => {
        rememberTab(tab);
        if (tab?.url) reevaluateTabContext(tab.id, tab.url);
      }).catch(() => {});
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
        contactName: dealCtx?.contactName || null,
        contactEmail: dealCtx?.contactEmail || null,
        contactId: dealCtx?.contactId || null,
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
        companyContacts: Array.isArray(companyCtx?.contacts) ? companyCtx.contacts : [],
        _enrichedKey: key,
      };
    }
  } catch (e) {
    console.warn('[BG] Failed to enrich page context:', e);
  }
  return ctx;
}

function applyContextAsync(ctx) {
  updateState({ context: ctx });
  fetchRecordingsIfNeeded(ctx);
  const key = ctx?.recordId ? `${ctx.objectType}:${ctx.recordId}` : null;
  if (!key || state.context?._enrichedKey === key) return;
  enrichPageContext(ctx).then((enriched) => {
    // Only apply if user is still on the same record
    const current = state.context;
    if (!current || current.recordId !== enriched.recordId || current.objectType !== enriched.objectType) {
      return;
    }
    updateState({ context: enriched });
  });
}

function recordingsEndpoint(ctx) {
  if (ctx?.objectType === 'contact' && ctx.recordId) {
    return `/crm/hubspot/contacts/${ctx.recordId}/recordings`;
  }
  if (ctx?.objectType === 'deal' && ctx.recordId) {
    return `/crm/hubspot/deals/${ctx.recordId}/recordings`;
  }
  return null;
}

function fetchRecordingsIfNeeded(ctx, { force = false } = {}) {
  const endpoint = recordingsEndpoint(ctx);
  if (!endpoint) {
    if (recordingsKey) {
      recordingsKey = null;
      updateState({ recordings: [], recordingsLoading: false });
    }
    return;
  }

  const key = `${ctx.objectType}:${ctx.recordId}`;
  if (!force && recordingsKey === key) return;

  const prevKey = recordingsKey;
  recordingsKey = key;
  updateState({
    recordingsLoading: true,
    recordings: prevKey === key ? (state.recordings || []) : [],
  });

  api.get(endpoint)
    .then((items) => {
      if (recordingsKey !== key) return;
      const list = Array.isArray(items)
        ? items.map((rec) => ({ ...rec, timestamp: rec.timestamp || rec.timestamp_ms || null }))
        : [];
      updateState({ recordings: list, recordingsLoading: false });
    })
    .catch((e) => {
      console.warn('[BG] Failed to load recordings:', e);
      if (recordingsKey !== key) return;
      updateState({ recordings: [], recordingsLoading: false });
    });
}

function reevaluateTabContext(tabId, url) {
  if (!url) return;

  const ctx = parseHubSpotUrl(url);
  const watchableTypes = ['deal', 'contact'];
  const recordType = ctx?.objectType;
  const recordId = watchableTypes.includes(recordType) ? ctx.recordId : null;

  // Always refresh page context (even during review) so "use contact on this page" stays accurate.
  // Never start/stop watches or change status while a flow is active.
  const flowBusy =
    state.isRecording ||
    state.status === 'processing' ||
    state.status === 'review' ||
    state.status === 'success';

  if (flowBusy) {
    if (ctx?.recordId) applyContextAsync(ctx);
    else if (!ctx) {
      recordingsKey = null;
      updateState({ context: null, recordings: [], recordingsLoading: false });
    }
    return;
  }

  if (recordId) {
    applyContextAsync(ctx);
    startCallWatch(recordId, recordType);
  } else {
    clearCallWatch();
    if (ctx?.objectType === 'company' && ctx.recordId) applyContextAsync(ctx);
    else {
      recordingsKey = null;
      updateState({ context: ctx || null, recordings: [], recordingsLoading: false });
    }
  }
}

chrome.tabs.onActivated.addListener(({ tabId }) => {
  lastActiveTabId = tabId;
  chrome.tabs.get(tabId, (tab) => {
    if (chrome.runtime.lastError) return; // tab may be gone
    reevaluateTabContext(tabId, tab?.url);
  });
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tabId !== lastActiveTabId) return;
  // HubSpot SPA: URL can change without a document reload
  if (changeInfo.url) {
    reevaluateTabContext(tabId, changeInfo.url);
    return;
  }
  if (changeInfo.status === 'complete' && tab?.url) {
    reevaluateTabContext(tabId, tab.url);
  }
});

chrome.windows.onFocusChanged.addListener(() => seedActiveTab());
chrome.runtime.onStartup.addListener(seedActiveTab);
seedActiveTab();

// ============================================
// HOTKEY COMMAND
// ============================================
chrome.commands.onCommand.addListener((command) => {
  if (command === 'toggle-recording') {
    openExtensionUI();
    handleToggleRecording();
  }
});
