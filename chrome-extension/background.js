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
  syncResult: null
};

/** Cached for sidePanel.open – must be called synchronously in user gesture, no await before it */
let lastActiveTabId = null;

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
    chrome.tabs.create({ url: chrome.runtime.getURL('popup/index.html') }).catch(() => {});
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
  
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const context = tab?.url ? parseHubSpotUrl(tab.url) : null;

    await getOffscreenDocument();
    chrome.runtime.sendMessage({ target: 'offscreen', type: 'START_RECORDING' });
    
    updateState({ 
      isRecording: true, 
      status: 'recording', 
      finalTranscript: '',
      interimTranscript: '',
      context,
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
    
    updateState({ currentMemoId: result.id, status: 'processing' });
    showNotification('Upload Complete', 'AI is analyzing your memo...');
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

      if (memo.status === 'pending_review') {
        clearInterval(interval);
        showNotification('Ready for Review', 'Click to review and sync to CRM.');
        updateState({ status: 'review', currentMemoId: memoId });
        // No user gesture here; open tab (sidePanel.open would fail)
        chrome.tabs.create({ url: chrome.runtime.getURL('popup/index.html') }).catch(() => {});
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
    case 'GET_STATE':
      sendResponse(state);
      break;
    
    case 'SET_STATE':
      updateState({
        ...message.state,
        ...(message.state?.status === 'review' && { context: null }),
      });
      break;
    
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
      const previewUrl = `/memos/${message.memoId}/preview${message.dealId ? `?deal_id=${message.dealId}` : ''}`;
      api.get(previewUrl)
        .then(sendResponse)
        .catch(e => sendResponse({ error: e.message }));
      return true;

    case 'APPROVE_SYNC':
      api.post(`/memos/${message.memoId}/approve`, { 
        deal_id: message.dealId,
        is_new_deal: message.isNewDeal 
      })
        .then(result => {
          updateState({ status: 'success', syncResult: result });
          sendResponse({ success: true, result });
        })
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

    case 'DISCARD_MEMO':
      updateState({ 
        status: 'idle', 
        currentMemoId: null, 
        syncResult: null,
        context: null,
        finalTranscript: '',
        interimTranscript: ''
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
chrome.tabs.onActivated.addListener((info) => { lastActiveTabId = info.tabId; });
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
