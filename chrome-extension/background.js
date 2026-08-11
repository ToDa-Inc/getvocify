/**
 * Service Worker for Vocify Chrome Extension
 * 
 * The "Brain" of the extension. Maintains state even when popup is closed.
 */

import { api } from './lib/api.js';
import { parseHubSpotUrl } from './lib/hubspot-parser.js';

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
};

/** Cached for sidePanel.open – must be called synchronously in user gesture, no await before it */
let lastActiveTabId = null;

let callWatchTimerId = null;
let callWatchingRecordId = null;  // deal or contact id being watched
let callWatchingRecordType = null; // 'deal' | 'contact'

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
  updateState({ watchingForRecording: false });
}

/**
 * Start polling for a HubSpot call memo on a deal or contact page.
 * Supports both deal and contact record types.
 */
function startCallWatch(recordId, recordType) {
  if (!recordId) return;
  if (callWatchingRecordId === recordId && callWatchTimerId != null) return;
  clearCallWatch();
  callWatchingRecordId = recordId;
  callWatchingRecordType = recordType || 'deal';
  updateState({ watchingForRecording: true });

  let pollCount = 0;

  const scheduleNext = (ms) => {
    callWatchTimerId = setTimeout(tick, ms);
  };

  async function tick() {
    callWatchTimerId = null;
    try {
      const { accessToken } = await api.getTokens();
      if (!accessToken) {
        scheduleNext(10000);
        return;
      }
      // Build endpoint based on record type
      const endpoint = callWatchingRecordType === 'contact'
        ? `/crm/hubspot/contacts/${callWatchingRecordId}/call-memo`
        : `/crm/hubspot/deals/${callWatchingRecordId}/call-memo`;
      const res = await api.get(endpoint);
      if (res.memo_id) {
        const st = res.status;
        // Already completed memos — keep watching for the next new call
        if (st === 'approved' || st === 'rejected') {
          pollCount += 1;
          if (pollCount > 48) { clearCallWatch(); return; }
          scheduleNext(pollCount <= 24 ? 5000 : 20000);
          return;
        }
        clearCallWatch();
        if (st === 'transcribing' || st === 'uploading' || st === 'extracting') {
          updateState({ status: 'processing', currentMemoId: res.memo_id, watchingForRecording: false, processingSource: 'hubspot_call' });
          showNotification('Vocify', 'Analyzing your call recording...');
          startPolling(res.memo_id);
        } else if (st === 'pending_transcript' || st === 'pending_review') {
          updateState({ status: 'review', currentMemoId: res.memo_id, watchingForRecording: false });
          showNotification('Call ready', 'Review your transcript.');
        }
        return;
      }
    } catch (e) {
      console.warn('[BG] call-memo poll error:', e);
    }
    pollCount += 1;
    if (pollCount > 48) {
      clearCallWatch();
      showNotification('Vocify', 'No call recording found. Reopen the panel to try again.');
      return;
    }
    const delay = pollCount <= 24 ? 2000 : 10000;
    scheduleNext(delay);
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
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
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
  let pollCount = 0;
  console.log('[BG] Starting polling for memo:', memoId);
  
  const interval = setInterval(async () => {
    try {
      const memo = await api.getMemo(memoId);
      pollCount++;
      console.log('[BG] Poll #', pollCount, 'status:', memo.status);

        if (memo.status === 'pending_review' || memo.status === 'pending_transcript') {
        clearInterval(interval);
        showNotification('Ready for Review', 'Review and confirm your transcript.');
        updateState({ status: 'review', currentMemoId: memoId });
        // Stay in extension: side panel (if open) receives STATE_UPDATED; user clicks icon to open
      } else if (memo.status === 'approved') {
        clearInterval(interval);
        updateState({ status: 'success', syncResult: memo });
      } else if (memo.status === 'failed') {
        clearInterval(interval);
        updateState({ status: 'idle', currentMemoId: null });
        showNotification('Analysis Failed', memo.errorMessage || 'Unknown error');
      } else if (pollCount > 60) {
        clearInterval(interval);
        updateState({ status: 'idle', currentMemoId: null });
        showNotification('Timeout', 'Processing took too long.');
      }
    } catch (e) {
      console.error('[BG] Polling error:', e);
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
      if (state.status === 'review' && state.currentMemoId) {
        chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
          if (tab?.url) {
            const ctx = parseHubSpotUrl(tab.url);
            if (ctx?.objectType === 'deal' && ctx?.recordId) {
              state = { ...state, context: ctx };
              updateState({ context: ctx });
            }
          }
          sendResponse(state);
        });
        return true;
      }
      if (state.status === 'idle' && !state.isRecording) {
        chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
          const ctx = tab?.url ? parseHubSpotUrl(tab.url) : null;
          if (!ctx || ctx.objectType !== 'deal' || !ctx.recordId) {
            clearCallWatch();
            updateState({ context: ctx });
          } else {
            updateState({ context: ctx });
            startCallWatch(ctx.recordId);
          }
          sendResponse(state);
        });
        return true;
      }
      sendResponse(state);
      break;
    }
    
    case 'SET_STATE': {
      const newState = { ...message.state };
      // When opening a memo for review, refresh context from active tab (deal on current page)
      if (newState.status === 'review' && newState.currentMemoId) {
        chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
          if (tab?.url) {
            const ctx = parseHubSpotUrl(tab.url);
            if (ctx?.objectType === 'deal' && ctx?.recordId) {
              newState.context = ctx;
            }
          }
          updateState(newState);
        });
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
          extraction: message.extraction 
        })
          .then(sendResponse)
          .catch(e => sendResponse({ error: e.message }));
      } else {
        const params = new URLSearchParams();
        if (message.dealId) params.set('deal_id', message.dealId);
        if (message.contactId) params.set('contact_id', message.contactId);
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
      })
        .then(result => {
          updateState({ status: 'success', syncResult: result });
          sendResponse({ success: true, result });
        })
        .catch(e => sendResponse({ error: e.message }));
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

    case 'GET_CRM_CONFIG':
      api.get('/crm/hubspot/configuration')
        .then(sendResponse)
        .catch(e => sendResponse({ error: e.message }));
      return true;

    case 'GET_RECENT_MEMOS':
      api.get('/memos')
        .then(results => {
          // Only return the last 5
          const recent = (results || []).slice(0, 5);
          sendResponse(recent);
        })
        .catch(e => sendResponse({ error: e.message }));
      return true;

    case 'STOP_CALL_WATCH':
      clearCallWatch();
      sendResponse({ ok: true });
      break;

    case 'DISCARD_MEMO':
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
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const tab = tabs[0];
        if (tab?.url) reevaluateTabContext(tab.id, tab.url);
      });
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
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) lastActiveTabId = tabs[0].id;
  });
}

// ============================================
// TAB CONTEXT TRACKING
// Re-evaluates the deal watcher whenever the user navigates or switches tabs.
// Only acts when idle — never interrupts an active recording or review.
// ============================================
function reevaluateTabContext(tabId, url) {
  if (!url) return;
  // Never interrupt an active flow
  if (state.isRecording || state.status === 'processing' || state.status === 'review' || state.status === 'success') return;

  const ctx = parseHubSpotUrl(url);
  const watchableTypes = ['deal', 'contact'];
  const recordType = ctx?.objectType;
  const recordId = watchableTypes.includes(recordType) ? ctx.recordId : null;

  if (recordId) {
    // Switched to a deal or contact page — start (or switch) the watcher
    updateState({ context: ctx });
    startCallWatch(recordId, recordType);
  } else {
    // Left a watchable page — stop watching, update context
    clearCallWatch();
    updateState({ context: ctx || null });
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
  // Only care about the active tab completing a navigation
  if (tabId !== lastActiveTabId) return;
  if (changeInfo.status !== 'complete') return;
  reevaluateTabContext(tabId, tab?.url);
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
