/**
 * Popup Script - Mini-Dashboard
 * 
 * Mirrors the dashboard UX in a compact popup format.
 */

import { api } from '../lib/api.js';

// ============================================
// SCREEN ELEMENTS
// ============================================
const screens = {
  loading: document.getElementById('screen-loading'),
  login: document.getElementById('screen-login'),
  record: document.getElementById('screen-record'),
  processing: document.getElementById('screen-processing'),
  review: document.getElementById('screen-review'),
  success: document.getElementById('screen-success')
};

// ============================================
// UI ELEMENTS
// ============================================
const recordButton = document.getElementById('record-button');
const liveTranscriptText = document.getElementById('live-transcript-text');
const liveTranscriptContainer = document.getElementById('live-transcript-container');
const shortcutBox = document.getElementById('shortcut-box');
const dealSearchInput = document.getElementById('deal-search-input');
const searchResultsBox = document.getElementById('search-results');
const proposedUpdatesList = document.getElementById('proposed-updates-list');
const approveSyncButton = document.getElementById('approve-sync-button');

let currentMemoId = null;
let currentDealId = null;
let searchTimeout = null;
let previewLoaded = false;

// ============================================
// SCREEN MANAGEMENT
// ============================================
function showScreen(screenKey) {
  Object.keys(screens).forEach(key => {
    if (screens[key]) {
      screens[key].style.display = key === screenKey ? 'flex' : 'none';
    }
  });
}

// ============================================
// RENDER STATE (Core Logic)
// ============================================
function renderState(state) {
  console.log('[Popup] Rendering state:', state.status, 'isRecording:', state.isRecording);
  
  // Build full transcript for display
  const fullTranscript = [
    state.finalTranscript || '',
    state.interimTranscript || ''
  ].filter(Boolean).join(' ').trim();

  // Recording UI
  if (state.isRecording) {
    showScreen('record');
    recordButton.classList.add('recording');
    document.getElementById('record-status-label').textContent = 'Recording...';
    document.getElementById('record-header-subtitle').textContent = 'Recording';
    liveTranscriptContainer.style.display = 'block';
    shortcutBox.style.display = 'none';

    const dealContextBadge = document.getElementById('deal-context-badge');
    if (dealContextBadge) {
      const isDealPage = state.context?.objectType === 'deal';
      dealContextBadge.style.display = isDealPage ? 'flex' : 'none';
      if (isDealPage) dealContextBadge.textContent = 'Target: Deal on this page';
    }

    // Show transcript with interim text styled differently
    liveTranscriptText.innerHTML = state.finalTranscript
      ? `${state.finalTranscript} <span style="opacity:0.5">${state.interimTranscript || ''}</span>`
      : `<span style="opacity:0.5">${state.interimTranscript || 'Listening...'}</span>`;
    
    liveTranscriptContainer.scrollTop = liveTranscriptContainer.scrollHeight;
    return;
  }

  // Not recording - reset button state
  recordButton.classList.remove('recording');
  document.getElementById('record-status-label').textContent = 'Tap to record';
  document.getElementById('record-header-subtitle').textContent = 'Ready to record';
  const dealContextBadge = document.getElementById('deal-context-badge');
  if (dealContextBadge) dealContextBadge.style.display = 'none';

  // Screen transitions based on status
  switch (state.status) {
    case 'idle':
      showScreen('record');
      liveTranscriptContainer.style.display = 'none';
      shortcutBox.style.display = 'block';
      previewLoaded = false; // Reset for next recording
      currentMemoId = null;
      loadRecentMemos(); // Refresh recent list
      break;
      
    case 'processing':
      showScreen('processing');
      break;
      
    case 'review':
      showScreen('review');
      if (state.currentMemoId && (!previewLoaded || currentMemoId !== state.currentMemoId)) {
        currentMemoId = state.currentMemoId;
        previewLoaded = true;
        const dealId = state.context?.objectType === 'deal' ? state.context.recordId : null;
        loadPreview(currentMemoId, dealId);
      }
      break;
      
    case 'success':
      showScreen('success');
      renderSuccess(state.syncResult);
      break;
  }
}

// ============================================
// PREVIEW & DEAL LOGIC
// ============================================
async function loadRecentMemos() {
  const listElement = document.getElementById('recent-memos-list');
  if (!listElement) return;

  try {
    const memos = await chrome.runtime.sendMessage({ type: 'GET_RECENT_MEMOS' });
    
    if (memos && !memos.error && Array.isArray(memos)) {
      if (memos.length === 0) {
        listElement.innerHTML = '<p class="body-muted" style="text-align: center; padding: 10px;">No memos yet.</p>';
        return;
      }

      listElement.innerHTML = '';
      memos.forEach(memo => {
        const item = document.createElement('div');
        item.className = 'memo-item';
        
        const date = new Date(memo.created_at).toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });

        let statusClass = 'status-processing';
        let statusText = memo.status.replace(/_/g, ' ');
        if (memo.status === 'pending_review') statusClass = 'status-pending';
        if (memo.status === 'approved') statusClass = 'status-approved';
        if (memo.status === 'failed') statusClass = 'status-failed';

        item.innerHTML = `
          <div class="memo-info">
            <span class="memo-date">${date}</span>
            <span class="memo-status">${memo.transcript ? memo.transcript.substring(0, 30) + '...' : 'No transcript'}</span>
          </div>
          <span class="status-pill ${statusClass}">${statusText}</span>
        `;
        
        item.onclick = () => {
          if (memo.status === 'pending_review') {
            chrome.runtime.sendMessage({ 
              type: 'SET_STATE', 
              state: { status: 'review', currentMemoId: memo.id } 
            });
          }
        };
        listElement.appendChild(item);
      });
    }
  } catch (e) {
    console.error('[Popup] Failed to load recent memos:', e);
  }
}

async function loadPreview(memoId, dealId = null) {
  console.log('[Popup] Loading preview for memo:', memoId, 'dealId:', dealId);
  
  // Show loading state
  document.getElementById('target-deal-name').textContent = 'Loading...';
  document.getElementById('target-deal-reason').textContent = '';
  proposedUpdatesList.innerHTML = '<div class="spinner" style="margin: 20px auto;"></div>';
  
  try {
    const preview = await chrome.runtime.sendMessage({ 
      type: 'GET_PREVIEW', 
      memoId, 
      dealId 
    });
    
    console.log('[Popup] Preview response:', preview);

    if (preview && !preview.error) {
      previewLoaded = true;
      const match = preview.selected_deal;
      currentDealId = match ? match.deal_id : null;
      
      document.getElementById('target-deal-name').textContent = match ? match.deal_name : 'New Deal';
      const reasonText = match
        ? (match.match_reason === 'Manual Selection' ? 'From current page' : `Matched via ${(match.match_reason || 'AI').toLowerCase()}`)
        : 'A new record will be created';
      document.getElementById('target-deal-reason').textContent = reasonText;
      
      // Inject proposed updates
      proposedUpdatesList.innerHTML = '';
      const updates = preview.proposed_updates || [];
      
      if (updates.length === 0) {
        proposedUpdatesList.innerHTML = '<p class="body-muted" style="padding: 12px;">No field updates extracted.</p>';
      } else {
        updates.forEach(update => {
          const div = document.createElement('div');
          div.className = 'update-item';
          div.innerHTML = `
            <p class="update-label">${update.field_label || update.field_name}</p>
            <p class="update-value">${update.new_value || '—'}</p>
            ${update.current_value ? `<p class="update-current">Was: ${update.current_value}</p>` : ''}
          `;
          proposedUpdatesList.appendChild(div);
        });
      }
    } else {
      console.error('[Popup] Preview error:', preview?.error);
      document.getElementById('target-deal-name').textContent = 'Error';
      proposedUpdatesList.innerHTML = '<p class="body-muted" style="padding: 12px; color: #ef4444;">Failed to load preview.</p>';
    }
  } catch (e) {
    console.error('[Popup] Failed to load preview:', e);
    document.getElementById('target-deal-name').textContent = 'Error';
    proposedUpdatesList.innerHTML = '<p class="body-muted" style="padding: 12px; color: #ef4444;">Error loading preview.</p>';
  }
}

async function searchDeals(query) {
  if (!query || query.length < 2) {
    searchResultsBox.innerHTML = '';
    searchResultsBox.style.display = 'none';
    return;
  }
  
  console.log('[Popup] Searching for:', query);
  
  try {
    const results = await chrome.runtime.sendMessage({ type: 'SEARCH_DEALS', query });
    console.log('[Popup] Search results received:', results);
    console.log('[Popup] Is array?', Array.isArray(results), 'Length:', results?.length);
    
    searchResultsBox.innerHTML = '';
    
    if (results && !results.error && Array.isArray(results) && results.length > 0) {
      console.log('[Popup] Showing', results.length, 'results');
      searchResultsBox.style.display = 'block';
      
      results.forEach(deal => {
        console.log('[Popup] Adding deal:', deal.deal_name);
        const item = document.createElement('div');
        item.className = 'search-item';
        item.innerHTML = `
          <p>${deal.deal_name}</p>
          <span>${deal.stage?.replace(/_/g, ' ') || 'No stage'}</span>
        `;
        item.onclick = () => {
          previewLoaded = false;
          loadPreview(currentMemoId, deal.deal_id);
          document.getElementById('deal-search-box').style.display = 'none';
          dealSearchInput.value = '';
          searchResultsBox.innerHTML = '';
          searchResultsBox.style.display = 'none';
        };
        searchResultsBox.appendChild(item);
      });
    } else if (results && !results.error && Array.isArray(results) && results.length === 0) {
      // Show "no results" message
      console.log('[Popup] No deals found');
      searchResultsBox.style.display = 'block';
      searchResultsBox.innerHTML = '<p class="body-muted" style="padding: 12px; text-align: center;">No deals found</p>';
    } else {
      console.log('[Popup] Invalid results or error:', results);
      searchResultsBox.style.display = 'none';
    }
  } catch (e) {
    console.error('[Popup] Search error:', e);
    searchResultsBox.style.display = 'none';
  }
}

// ============================================
// SUCCESS SCREEN
// ============================================
function renderSuccess(result) {
  const msg = document.getElementById('success-message');
  const btn = document.getElementById('view-in-hubspot');
  
  if (result && result.deal_url) {
    msg.textContent = `Updated "${result.deal_name || 'deal'}" in HubSpot.`;
    btn.href = result.deal_url;
    btn.style.display = 'block';
  } else {
    msg.textContent = 'CRM updated successfully!';
    btn.style.display = 'none';
  }
}

// ============================================
// EVENT LISTENERS
// ============================================

// Record button
recordButton.addEventListener('click', async () => {
  const state = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
  
  if (state.isRecording) {
    chrome.runtime.sendMessage({ type: 'TOGGLE_RECORDING' });
  } else {
    // Check mic permission first
    try {
      const permResult = await navigator.permissions.query({ name: 'microphone' });
      if (permResult.state === 'granted') {
        chrome.runtime.sendMessage({ type: 'TOGGLE_RECORDING' });
      } else {
        // Open setup page for permission
        chrome.tabs.create({ url: chrome.runtime.getURL('setup.html') });
      }
    } catch {
      // Some browsers don't support permission query
      chrome.runtime.sendMessage({ type: 'TOGGLE_RECORDING' });
    }
  }
});

// Change deal button
document.getElementById('btn-change-deal')?.addEventListener('click', () => {
  const box = document.getElementById('deal-search-box');
  box.style.display = box.style.display === 'none' ? 'block' : 'none';
  if (box.style.display === 'block') {
    dealSearchInput.focus();
  }
});

// Deal search input
dealSearchInput?.addEventListener('input', (e) => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => searchDeals(e.target.value), 300);
});

// Approve sync
approveSyncButton?.addEventListener('click', async () => {
  approveSyncButton.disabled = true;
  approveSyncButton.textContent = 'Syncing...';
  
  try {
    await chrome.runtime.sendMessage({ 
      type: 'APPROVE_SYNC', 
      memoId: currentMemoId, 
      dealId: currentDealId,
      isNewDeal: !currentDealId
    });
  } catch (e) {
    console.error('[Popup] Approve error:', e);
  } finally {
    approveSyncButton.disabled = false;
    approveSyncButton.textContent = 'Confirm & Update CRM';
  }
});

// Discard button
document.getElementById('discard-button')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'DISCARD_MEMO' });
});

// Success done button
document.getElementById('success-done-button')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'DISCARD_MEMO' });
});

// ============================================
// MESSAGE LISTENER (State Updates)
// ============================================
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'STATE_UPDATED') {
    renderState(message.state);
  }
});

// ============================================
// LOGIN HANDLERS
// ============================================
document.getElementById('login-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('button');
  const errorBox = document.getElementById('login-error');
  
  btn.disabled = true;
  errorBox.style.display = 'none';
  
  try {
    await api.login(
      document.getElementById('login-email').value, 
      document.getElementById('login-password').value
    );
    init();
  } catch (err) {
    errorBox.textContent = 'Login failed. Check your credentials.';
    errorBox.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('logout-button')?.addEventListener('click', async () => {
  await api.clearTokens();
  showScreen('login');
});

// ============================================
// INIT
// ============================================
async function init() {
  showScreen('loading');
  
  const { accessToken } = await api.getTokens();
  if (!accessToken) {
    showScreen('login');
    return;
  }

  try {
    const user = await api.getCurrentUser();
    document.getElementById('user-name').textContent = user.full_name || 'User';
    document.getElementById('user-email').textContent = user.email;
    
    // Get current state from background
    const state = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
    renderState(state);
  } catch (e) {
    console.error('[Popup] Init error:', e);
    showScreen('login');
  }
}

init();
