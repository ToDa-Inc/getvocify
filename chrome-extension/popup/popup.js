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
let sessionHeartbeatId = null;
/** Cached preview data for extraction merge */
let lastPreviewData = null;
/** Edits/removals from proposed updates (index → update or null if removed) */
let editedProposedUpdates = null;
/** Click-outside handler for Add field dropdown */
let addFieldCloseHandler = null;

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

function showExtractionError(message) {
  const banner = document.getElementById('extraction-error-banner');
  const text = document.getElementById('extraction-error-text');
  if (banner && text) {
    text.textContent = message;
    banner.style.display = 'block';
  }
}

function hideExtractionError() {
  const banner = document.getElementById('extraction-error-banner');
  if (banner) banner.style.display = 'none';
}

/** Set processing screen text: 'transcribing' (audio→transcript) or 'extracting' (transcript→CRM fields) */
function setProcessingScreenMode(mode) {
  const sub = document.getElementById('processing-subtitle');
  const title = document.getElementById('processing-title');
  const msg = document.getElementById('processing-message');
  if (mode === 'extracting') {
    if (sub) sub.textContent = 'Extracting';
    if (title) title.textContent = 'AI is analyzing your transcript...';
    if (msg) msg.textContent = 'Extracting CRM fields. Ready in a moment.';
  } else {
    if (sub) sub.textContent = 'Transcribing';
    if (title) title.textContent = 'Converting speech to text...';
    if (msg) msg.textContent = 'Your transcript will be ready to review in a moment.';
  }
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

  const pasteSection = document.getElementById('paste-transcript-section');
  const pasteToggle = document.getElementById('paste-transcript-toggle');
  const mainActions = document.querySelector('.main-actions');
  const shortcutBox = document.getElementById('shortcut-box');
  const recentMemos = document.getElementById('recent-memos-section');

  // Reset visibility
  if (pasteSection) pasteSection.style.display = 'none';
  if (pasteToggle) pasteToggle.style.display = 'flex';
  if (mainActions) mainActions.style.display = 'flex';
  if (shortcutBox) shortcutBox.style.display = 'block';
  if (recentMemos) recentMemos.style.display = 'block';

  // Recording UI
  if (state.isRecording) {
    showScreen('record');
    recordButton.classList.add('recording');
    document.getElementById('record-status-label').textContent = 'Recording...';
    document.getElementById('record-header-subtitle').textContent = 'Recording';
    liveTranscriptContainer.style.display = 'block';
    
    // Hide non-recording elements
    if (shortcutBox) shortcutBox.style.display = 'none';
    if (recentMemos) recentMemos.style.display = 'none';
    if (pasteToggle) pasteToggle.style.display = 'none';
    if (pasteSection) pasteSection.style.display = 'none';

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
      stopSessionHeartbeat();
      showScreen('record');
      liveTranscriptContainer.style.display = 'none';
      
      // Ensure all idle elements are visible
      if (shortcutBox) shortcutBox.style.display = 'block';
      if (recentMemos) recentMemos.style.display = 'block';
      if (pasteToggle) pasteToggle.style.display = 'flex';
      if (mainActions) mainActions.style.display = 'flex';
      if (pasteSection) pasteSection.style.display = 'none';

      previewLoaded = false;
      currentMemoId = null;
      loadRecentMemos(); // Refresh recent list
      break;
      
    case 'processing':
      setProcessingScreenMode('transcribing'); // Background polling: audio being transcribed
      showScreen('processing');
      break;
      
    case 'review':
      showScreen('review');
      if (state.currentMemoId && currentMemoId !== state.currentMemoId) {
        currentMemoId = state.currentMemoId;
        previewLoaded = false;
        lastPreviewData = null;
        editedProposedUpdates = null;
      }
      if (state.currentMemoId) {
        handleReviewState(state.currentMemoId, state.context);
      }
      break;
      
    case 'success':
      stopSessionHeartbeat();
      showScreen('success');
      renderSuccess(state.syncResult);
      break;
  }
}

// ============================================
// REVIEW WIZARD HELPERS
// ============================================
function startSessionHeartbeat() {
  if (sessionHeartbeatId) return;
  sessionHeartbeatId = setInterval(() => {
    api.getCurrentUser().catch(() => {});
  }, 90_000);
}
function stopSessionHeartbeat() {
  if (sessionHeartbeatId) {
    clearInterval(sessionHeartbeatId);
    sessionHeartbeatId = null;
  }
}

/** Route review to pending-transcript or proposed-changes based on memo status */
async function handleReviewState(memoId, context) {
  startSessionHeartbeat();
  try {
    const memo = await api.getMemo(memoId);
    const status = memo?.status || '';
    const pendingTranscript = status === 'pending_transcript';

    const pendingSection = document.getElementById('pending-transcript-section');
    const proposedMain = document.getElementById('proposed-changes-main');
    const reviewActions = document.getElementById('review-actions');

    if (pendingTranscript) {
      pendingSection.style.display = 'block';
      proposedMain.style.display = 'none';
      reviewActions.style.display = 'none';
      loadTranscriptForReview(memoId);
    } else {
      pendingSection.style.display = 'none';
      proposedMain.style.display = 'block';
      reviewActions.style.display = 'flex';
      const onDealPage = context?.objectType === 'deal' && context?.recordId;
      const dealIdToLoad = onDealPage ? context.recordId : currentDealId;
      if (!previewLoaded || currentMemoId !== memoId || (onDealPage && currentDealId !== context?.recordId)) {
        currentMemoId = memoId;
        currentDealId = onDealPage ? context.recordId : currentDealId;
        previewLoaded = true;
        await loadPreview(memoId, dealIdToLoad, null);
      }
      showUseCurrentDealOption(onDealPage ? context : null);
      const transcriptEl = document.getElementById('transcript-expanded');
      const preview = lastPreviewData;
      if (transcriptEl && preview?.transcript) {
        transcriptEl.textContent = preview.transcript;
      }
    }
  } catch (e) {
    console.error('[Popup] handleReviewState error:', e);
  }
}

/** Show "Use deal on this page" when user is on a HubSpot deal page but viewing different deal/new deal */
function showUseCurrentDealOption(context) {
  const opt = document.getElementById('use-current-deal-option');
  if (!opt) return;
  opt.style.display = context?.objectType === 'deal' && context?.recordId ? 'block' : 'none';
}

async function loadTranscriptForReview(memoId) {
  const el = document.getElementById('transcript-content');
  if (!el) return;
  el.value = 'Loading transcript...';
  el.readOnly = true;
  try {
    const memo = await api.getMemo(memoId);
    const status = memo?.status || '';
    el.value = memo?.transcript || 'No transcript available.';
    el.readOnly = status === 'pending_review'; // Editable only when pending_transcript
    if (memo?.status === 'failed') {
      showExtractionError(memo?.errorMessage || 'Extraction failed. Click Retry to try again.');
    } else if (memo?.status === 'extracting') {
      showExtractionError('Extraction is still in progress or stuck. Click Retry to try again.');
    } else {
      hideExtractionError();
    }
  } catch (e) {
    console.error('[Popup] Failed to load transcript:', e);
    el.value = 'Failed to load transcript.';
    el.readOnly = true;
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
        
        const date = new Date(memo.createdAt || memo.created_at).toLocaleDateString(undefined, {
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

async function loadPreview(memoId, dealId = null, extraction = null) {
  document.getElementById('target-deal-name').textContent = 'Loading...';
  document.getElementById('target-deal-reason').textContent = '';
  proposedUpdatesList.innerHTML = '<div class="spinner" style="margin: 20px auto;"></div>';

  try {
    const preview = await chrome.runtime.sendMessage({
      type: 'GET_PREVIEW',
      memoId,
      dealId,
      extraction: extraction || undefined
    });

    if (preview && !preview.error) {
      lastPreviewData = preview;
      previewLoaded = true;
      const match = preview.selected_deal;
      currentDealId = match ? match.deal_id : null;

      document.getElementById('target-deal-name').textContent = match ? match.deal_name : 'New Deal';
      const reasonText = match
        ? (match.match_reason === 'Manual Selection' ? 'From current page' : `Matched via ${(match.match_reason || 'AI').toLowerCase()}`)
        : 'A new record will be created';
      document.getElementById('target-deal-reason').textContent = reasonText;

      // Reset edited state when loading fresh preview
      editedProposedUpdates = null;
      renderProposedUpdates(preview.proposed_updates || [], preview.available_fields || []);
    } else {
      document.getElementById('target-deal-name').textContent = 'Error';
      proposedUpdatesList.innerHTML = '<p class="body-muted" style="padding: 12px; color: #ef4444;">Failed to load preview.</p>';
    }
  } catch (e) {
    console.error('[Popup] Failed to load preview:', e);
    document.getElementById('target-deal-name').textContent = 'Error';
    proposedUpdatesList.innerHTML = '<p class="body-muted" style="padding: 12px; color: #ef4444;">Error loading preview.</p>';
  }
}

function renderProposedUpdates(updates, availableFields) {
  proposedUpdatesList.innerHTML = '';
  const list = editedProposedUpdates !== null ? editedProposedUpdates : updates.map((u) => ({ ...u }));
  const filteredList = list.filter(u => u && !['contact_name', 'company_name', 'dealname'].includes(u.field_name));

  filteredList.forEach((update, idx) => {
      if (!update) return; // removed
      const hadExisting =
        update.current_value != null &&
        String(update.current_value).trim() !== '' &&
        String(update.current_value).trim() !== '(empty)';
      const isOverride = !!hadExisting;
      const isDealField = !update.field_name.startsWith('next_step_task_');

      const editIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>`;
      const removeIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>`;

      const div = document.createElement('div');
      div.className = 'update-item' + (isOverride ? ' override' : ' new');
      div.dataset.idx = String(idx);
      div.innerHTML = `
        <div class="update-content">
          <div class="update-header-row">
            <p class="update-label">${update.field_label || update.field_name}</p>
            ${isDealField ? `
              <div class="update-actions">
                <button class="update-action-btn edit" title="Edit">${editIcon}</button>
                <button class="update-action-btn remove" title="Remove">${removeIcon}</button>
              </div>
            ` : ''}
          </div>
          <p class="update-value">${escapeHtml(update.new_value || '—')}</p>
          ${hadExisting ? `<p class="update-current">Was: ${escapeHtml(update.current_value)}</p>` : ''}
          ${update.options && update.options.length ? `
            <div class="custom-select-wrapper" style="display:none;">
              <div class="custom-select" role="listbox">
                <button type="button" class="custom-select-trigger update-edit-input" aria-haspopup="listbox">—</button>
                <div class="custom-select-dropdown" role="listbox" aria-hidden="true">
                  <div class="custom-select-opt" data-value="">—</div>
                  ${update.options.map((o) => `<div class="custom-select-opt" data-value="${escapeHtml(o.value)}" data-label="${escapeHtml(o.label || o.value)}">${escapeHtml(o.label || o.value)}</div>`).join('')}
                </div>
              </div>
            </div>
          ` : `<input type="${update.field_type === 'number' ? 'number' : update.field_name === 'closedate' ? 'date' : 'text'}" class="update-edit-input" value="${escapeHtml(update.new_value || '')}" style="display:none;" />`}
        </div>
      `;

    const valueEl = div.querySelector('.update-value');
    const editInput = div.querySelector('input.update-edit-input, .custom-select-trigger');
    const customSelectWrapper = div.querySelector('.custom-select-wrapper');
    const customSelect = div.querySelector('.custom-select');
    const customTrigger = div.querySelector('.custom-select-trigger');
    const customDropdown = div.querySelector('.custom-select-dropdown');
    const customOpts = div.querySelectorAll('.custom-select-opt');
    const editBtn = div.querySelector('.update-action-btn.edit');
    const removeBtn = div.querySelector('.update-action-btn.remove');

    const closeCustomSelect = () => {
      if (customDropdown) customDropdown.classList.remove('open');
      document.removeEventListener('click', closeCustomSelectOutside);
    };
    const closeCustomSelectOutside = (e) => {
      if (!customSelect?.contains(e.target)) closeCustomSelect();
    };

    if (editBtn && editInput) {
      editBtn.onclick = () => {
        div.classList.add('editing');
        valueEl.style.display = 'none';
        if (customSelectWrapper) {
          customSelectWrapper.style.display = 'block';
          const opt = customOpts && Array.from(customOpts).find((o) => o.dataset.value === (update.new_value || ''));
          if (customTrigger) customTrigger.textContent = opt ? (opt.dataset.label || opt.dataset.value || '—') : '—';
        } else if (editInput.tagName === 'INPUT') {
          editInput.style.display = 'block';
          editInput.value = update.new_value || '';
          editInput.focus();
        }
      };
    }
    if (customTrigger && customDropdown && customOpts?.length) {
      customTrigger.onclick = (e) => {
        e.stopPropagation();
        customDropdown.classList.toggle('open');
        if (customDropdown.classList.contains('open')) setTimeout(() => document.addEventListener('click', closeCustomSelectOutside), 0);
        else document.removeEventListener('click', closeCustomSelectOutside);
      };
      customOpts.forEach((opt) => {
        opt.onclick = (e) => {
          e.stopPropagation();
          const v = opt.dataset.value ?? '';
          const label = opt.dataset.label || v || '—';
          if (editedProposedUpdates === null) editedProposedUpdates = list.map((u) => (u ? { ...u } : null));
          if (editedProposedUpdates[idx]) {
            editedProposedUpdates[idx].new_value = v;
            valueEl.textContent = label;
          }
          customTrigger.textContent = label;
          div.classList.remove('editing');
          valueEl.style.display = 'block';
          customSelectWrapper.style.display = 'none';
          closeCustomSelect();
        };
      });
    }
    if (editInput && editInput.tagName === 'INPUT') {
      const saveEdit = () => {
        const v = editInput.value?.trim() || '';
        div.classList.remove('editing');
        valueEl.style.display = 'block';
        if (customSelectWrapper) customSelectWrapper.style.display = 'none';
        editInput.style.display = 'none';
        if (editedProposedUpdates === null) editedProposedUpdates = list.map((u) => (u ? { ...u } : null));
        if (editedProposedUpdates[idx]) {
          editedProposedUpdates[idx].new_value = v;
          valueEl.textContent = v || '—';
        }
      };
      editInput.addEventListener('blur', saveEdit);
      editInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') saveEdit(); });
    }
    if (removeBtn) {
      removeBtn.onclick = () => {
        if (editedProposedUpdates === null) editedProposedUpdates = list.map((u) => (u ? { ...u } : null));
        editedProposedUpdates[idx] = null;
        const af = (lastPreviewData && lastPreviewData.available_fields) || [];
        renderProposedUpdates(editedProposedUpdates.filter(Boolean), af);
      };
    }

    proposedUpdatesList.appendChild(div);
  });

  const addBtn = document.getElementById('btn-add-field');
  const dropdown = document.getElementById('add-field-dropdown');
  if (availableFields.length > 0 && addBtn) {
    addBtn.style.display = 'block';
    addBtn.onclick = () => {
      const expanded = dropdown.style.display === 'block';
      dropdown.style.display = expanded ? 'none' : 'block';
      if (expanded) {
        if (addFieldCloseHandler) {
          document.removeEventListener('click', addFieldCloseHandler);
          addFieldCloseHandler = null;
        }
      } else {
        dropdown.innerHTML = availableFields
          .filter((f) => !list.some((u) => u && u.field_name === f.name))
          .map(
            (f) =>
              `<div class="add-field-opt" data-name="${escapeHtml(f.name)}" data-label="${escapeHtml(f.label)}" data-type="${escapeHtml(f.type)}">${escapeHtml(f.label)}</div>`
          )
          .join('');
        dropdown.querySelectorAll('.add-field-opt').forEach((opt) => {
          opt.onclick = () => {
            const newUpdate = {
              field_name: opt.dataset.name,
              field_label: opt.dataset.label,
              field_type: opt.dataset.type || 'string',
              current_value: null,
              new_value: '',
              options: availableFields.find((af) => af.name === opt.dataset.name)?.options
            };
            const nextList = editedProposedUpdates !== null ? [...editedProposedUpdates.filter(Boolean), newUpdate] : [...list, newUpdate];
            editedProposedUpdates = nextList;
            if (addFieldCloseHandler) {
              document.removeEventListener('click', addFieldCloseHandler);
              addFieldCloseHandler = null;
            }
            dropdown.style.display = 'none';
            renderProposedUpdates(editedProposedUpdates, availableFields);
          };
        });
        // Close dropdown when clicking outside
        if (addFieldCloseHandler) document.removeEventListener('click', addFieldCloseHandler);
        addFieldCloseHandler = (e) => {
          if (dropdown.style.display !== 'block') {
            addFieldCloseHandler = null;
            return;
          }
          if (addBtn.contains(e.target) || dropdown.contains(e.target)) return;
          dropdown.style.display = 'none';
          document.removeEventListener('click', addFieldCloseHandler);
          addFieldCloseHandler = null;
        };
        setTimeout(() => document.addEventListener('click', addFieldCloseHandler), 0);
      }
    }
  } else if (addBtn) {
    addBtn.style.display = 'none';
    dropdown.style.display = 'none';
  }

  if (list.filter(Boolean).length === 0 && !editedProposedUpdates) {
    proposedUpdatesList.innerHTML = '<p class="body-muted" style="padding: 12px;">No field updates extracted.</p>';
  }
}

function escapeHtml(s) {
  if (s == null) return '';
  const div = document.createElement('div');
  div.textContent = String(s);
  return div.innerHTML;
}

/** Build extraction from memo + edited proposed updates for approve API */
async function buildExtractionForApprove() {
  const preview = lastPreviewData;
  if (!preview) return undefined;

  const memo = await api.getMemo(currentMemoId);
  const base = memo?.extraction ? { ...memo.extraction } : {};
  const raw = { ...(base.raw_extraction || {}) };

  const updates = editedProposedUpdates !== null
    ? editedProposedUpdates.filter(Boolean)
    : (preview.proposed_updates || []);

  for (const u of updates) {
    const val = u.new_value?.trim() || null;
    if (!val && u.field_name !== 'description') continue;

    if (u.field_name === 'contact_name') {
      base.contactName = val;
    } else if (u.field_name === 'company_name') {
      base.companyName = val;
      raw.dealname = val;
    } else if (u.field_name === 'dealname') {
      base.companyName = val;
      raw.dealname = val;
    } else if (u.field_name === 'amount') {
      const amt = parseFloat(val);
      base.dealAmount = Number.isFinite(amt) ? amt : null;
      raw.amount = base.dealAmount;
    } else if (u.field_name === 'closedate') {
      base.closeDate = val;
      raw.closedate = val;
    } else if (u.field_name === 'dealstage') {
      base.dealStage = val;
      raw.dealstage = val;
    } else if (u.field_name === 'description') {
      base.summary = val || '';
      raw.description = val || '';
    } else if (u.field_name === 'hs_next_step') {
      raw.hs_next_step = val;
      base.nextSteps = val ? [val] : [];
    } else if (u.field_name.startsWith('next_step_task_')) {
      const steps = [...(base.nextSteps || [])];
      const i = parseInt(u.field_name.replace('next_step_task_', ''), 10);
      if (val && !Number.isNaN(i)) {
        steps[i] = val;
        base.nextSteps = steps.filter(Boolean);
        if (base.nextSteps[0]) raw.hs_next_step = base.nextSteps[0];
      }
    } else if (val) {
      raw[u.field_name] = u.field_type === 'number' ? (parseFloat(val) || null) : val;
    }
  }

  return { ...base, raw_extraction: raw };
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
          currentDealId = deal.deal_id;
          loadPreview(currentMemoId, deal.deal_id, null);
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
    } else if (results?.error) {
      console.error('[Popup] Search error:', results.error);
      searchResultsBox.style.display = 'block';
      searchResultsBox.innerHTML = `<p class="body-muted" style="padding: 12px; text-align: center; color: var(--destructive);">Search failed: ${escapeHtml(results.error)}</p>`;
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

// Paste transcript toggle
document.getElementById('paste-transcript-toggle')?.addEventListener('click', () => {
  const section = document.getElementById('paste-transcript-section');
  const toggle = document.getElementById('paste-transcript-toggle');
  const mainActions = document.querySelector('.main-actions');
  const shortcutBox = document.getElementById('shortcut-box');
  const recentMemos = document.getElementById('recent-memos-section');

  if (section && toggle) {
    section.style.display = 'block';
    toggle.style.display = 'none';
    if (mainActions) mainActions.style.display = 'none';
    if (shortcutBox) shortcutBox.style.display = 'none';
    if (recentMemos) recentMemos.style.display = 'none';
    document.getElementById('paste-transcript-input')?.focus();
  }
});

// Paste transcript cancel
document.getElementById('paste-transcript-cancel-btn')?.addEventListener('click', () => {
  const section = document.getElementById('paste-transcript-section');
  const toggle = document.getElementById('paste-transcript-toggle');
  const mainActions = document.querySelector('.main-actions');
  const shortcutBox = document.getElementById('shortcut-box');
  const recentMemos = document.getElementById('recent-memos-section');
  const input = document.getElementById('paste-transcript-input');

  if (section) section.style.display = 'none';
  if (toggle) toggle.style.display = 'flex';
  if (mainActions) mainActions.style.display = 'flex';
  if (shortcutBox) shortcutBox.style.display = 'block';
  if (recentMemos) recentMemos.style.display = 'block';
  if (input) input.value = '';
});

// Paste transcript import
document.getElementById('paste-transcript-import-btn')?.addEventListener('click', async () => {
  const input = document.getElementById('paste-transcript-input');
  const transcript = input?.value?.trim() || '';
  if (!transcript) return;

  const btn = document.getElementById('paste-transcript-import-btn');
  btn.disabled = true;
  btn.textContent = 'Importing...';
  setProcessingScreenMode('transcribing');
  showScreen('processing');

  try {
    const result = await api.uploadTranscript(transcript, 'meeting_transcript');
    currentMemoId = result.id;
    chrome.runtime.sendMessage({
      type: 'SET_STATE',
      state: { currentMemoId: result.id, status: 'review' },
    });
  } catch (err) {
    console.error('[Popup] Upload transcript failed:', err);
    showScreen('record');
    btn.disabled = false;
    btn.textContent = 'Import & Continue';
    const section = document.getElementById('paste-transcript-section');
    const toggle = document.getElementById('paste-transcript-toggle');
    if (section) section.style.display = 'block';
    if (toggle) toggle.style.display = 'none';
  }
});

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
    const extraction = await buildExtractionForApprove();
    await chrome.runtime.sendMessage({
      type: 'APPROVE_SYNC',
      memoId: currentMemoId,
      dealId: currentDealId,
      isNewDeal: !currentDealId,
      extraction: extraction || undefined
    });
  } catch (e) {
    console.error('[Popup] Approve error:', e);
  } finally {
    approveSyncButton.disabled = false;
    approveSyncButton.textContent = 'Confirm & Update CRM';
  }
});

// Discard button (step 2)
document.getElementById('discard-button')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'DISCARD_MEMO' });
});

// Review - confirm transcript (Extract & Continue)
document.getElementById('review-confirm-transcript-btn')?.addEventListener('click', async function () {
  const transcriptEl = document.getElementById('transcript-content');
  const transcript = transcriptEl?.value?.trim() || '';
  if (!transcript) return;
  this.disabled = true;
  this.textContent = 'Extracting...';
  hideExtractionError();
  try {
    await api.post(`/memos/${currentMemoId}/confirm-transcript`, { transcript });
    setProcessingScreenMode('extracting');
    showScreen('processing');
    let pollCount = 0;
    while (pollCount < 60) {
      await new Promise((r) => setTimeout(r, 2000));
      const memo = await api.getMemo(currentMemoId);
      if (memo.status === 'pending_review') {
        hideExtractionError();
        chrome.runtime.sendMessage({ type: 'GET_STATE' }).then((s) => renderState(s));
        return;
      }
      if (memo.status === 'failed') {
        showExtractionError(memo.errorMessage || 'Extraction failed.');
        showScreen('review');
        handleReviewState(currentMemoId, {});
        return;
      }
      pollCount++;
    }
    showExtractionError('Extraction is taking longer than expected. Click Retry to try again.');
    showScreen('review');
    handleReviewState(currentMemoId, {});
  } catch (err) {
    showExtractionError(err?.message || 'Something went wrong. Click Retry to try again.');
    showScreen('review');
    handleReviewState(currentMemoId, {});
  } finally {
    this.disabled = false;
    this.textContent = 'Extract & Continue';
  }
});

// Discard from pending transcript
document.getElementById('review-discard-btn')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'DISCARD_MEMO' });
});

// Retry extraction
document.getElementById('retry-extraction-btn')?.addEventListener('click', async function () {
  this.disabled = true;
  this.textContent = 'Retrying...';
  hideExtractionError();
  setProcessingScreenMode('extracting');
  showScreen('processing');
  try {
    const memo = await api.reExtract(currentMemoId);
    if (memo?.status === 'pending_review') {
      hideExtractionError();
      chrome.runtime.sendMessage({ type: 'GET_STATE' }).then((s) => renderState(s));
    } else {
      showExtractionError(memo?.errorMessage || 'Retry failed.');
      showScreen('review');
      handleReviewState(currentMemoId, {});
    }
  } catch (err) {
    showExtractionError(err?.message || 'Retry failed. Try again.');
    showScreen('review');
    handleReviewState(currentMemoId, {});
  } finally {
    this.disabled = false;
    this.textContent = 'Retry extraction';
  }
});

// Use current deal (from deal page)
document.getElementById('btn-use-current-deal')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'GET_STATE' }).then((state) => {
    const dealId = state.context?.objectType === 'deal' ? state.context.recordId : null;
    if (dealId) {
      currentDealId = dealId;
      previewLoaded = false;
      loadPreview(currentMemoId, dealId, null);
    }
  });
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
    const msg = err?.data?.detail || err?.message || 'Login failed. Check your credentials.';
    errorBox.textContent = typeof msg === 'string' ? msg : (Array.isArray(msg) ? msg[0] : 'Login failed');
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
    const nameEl = document.getElementById('user-name');
    if (nameEl) nameEl.textContent = user.full_name || 'User';
    const emailEl = document.getElementById('user-email');
    if (emailEl) emailEl.textContent = user.email;
    
    // Get current state from background
    const state = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
    renderState(state);
  } catch (e) {
    console.error('[Popup] Init error:', e);
    const isNetworkError = e?.message === 'Failed to fetch' || e?.name === 'TypeError' || (e?.message && /network|connection|refused/i.test(e.message));
    if (isNetworkError) {
      document.getElementById('loading-spinner').style.display = 'none';
      document.getElementById('loading-backend-error').style.display = 'block';
    } else {
      showScreen('login');
    }
  }
}

init();
