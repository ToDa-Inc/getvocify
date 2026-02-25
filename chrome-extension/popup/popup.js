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
/** Wizard: 1=transcript, 2=edit CRM fields, 3=deal target + proposed changes + confirm. Matches web app flow. */
let reviewStep = 1;
/** Edited extraction (Step 2) - passed to preview and approve */
let editedExtraction = null;

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
      stopSessionHeartbeat();
      showScreen('record');
      liveTranscriptContainer.style.display = 'none';
      shortcutBox.style.display = 'block';
      previewLoaded = false;
      reviewStep = 1;
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
        reviewStep = 1;
        previewLoaded = false;
        editedExtraction = null;
      }
      if (state.currentMemoId) {
        if (reviewStep === 1) {
          loadTranscriptForReview(state.currentMemoId);
          setReviewUIForStep(1);
        } else if (reviewStep === 2) {
          const dealId = state.context?.objectType === 'deal' ? state.context.recordId : null;
          loadExtractionForEdit(state.currentMemoId, dealId);
          setReviewUIForStep(2);
        } else {
          // Step 3: When on deal page, auto-use that deal; otherwise show match/search
          const onDealPage = state.context?.objectType === 'deal' && state.context?.recordId;
          const dealIdToLoad = onDealPage ? state.context.recordId : currentDealId;
          if (!previewLoaded || currentMemoId !== state.currentMemoId || (onDealPage && currentDealId !== state.context?.recordId)) {
            currentMemoId = state.currentMemoId;
            currentDealId = onDealPage ? state.context.recordId : currentDealId;
            previewLoaded = true;
            loadPreview(currentMemoId, dealIdToLoad, editedExtraction);
          }
          showUseCurrentDealOption(onDealPage ? null : state.context);
          setReviewUIForStep(3);
        }
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

function setReviewUIForStep(step) {
  startSessionHeartbeat();
  const step1Content = document.getElementById('review-step1-content');
  const step2Content = document.getElementById('review-step2-content');
  const step3Content = document.getElementById('review-step3-content');
  const step1Actions = document.getElementById('review-step1-actions');
  const step2Actions = document.getElementById('review-step2-actions');
  const step3Actions = document.getElementById('review-step3-actions');
  const stepLabel = document.getElementById('review-step-label');
  const labels = { 1: 'Step 1 of 3: Review transcript', 2: 'Step 2 of 3: Edit CRM fields', 3: 'Step 3 of 3: Deal target & confirm' };
  if (stepLabel) stepLabel.textContent = labels[step] || '';
  [step1Content, step2Content, step3Content].forEach((el, i) => {
    if (el) el.style.display = (i + 1 === step) ? 'block' : 'none';
  });
  [step1Actions, step2Actions, step3Actions].forEach((el, i) => {
    if (el) el.style.display = (i + 1 === step) ? 'flex' : 'none';
  });
}

function showUseCurrentDealOption(context) {
  const opt = document.getElementById('use-current-deal-option');
  if (!opt) return;
  if (context?.objectType === 'deal' && context?.recordId) {
    opt.style.display = 'block';
  } else {
    opt.style.display = 'none';
  }
}

/** Cached memo status for step 1 (pending_transcript = editable, pending_review = readonly) */
let memoStatusForStep1 = null;

async function loadTranscriptForReview(memoId) {
  const el = document.getElementById('transcript-content');
  if (!el) return;
  el.value = 'Loading transcript...';
  el.readOnly = true;
  try {
    const memo = await api.getMemo(memoId);
    memoStatusForStep1 = memo?.status || null;
    el.value = memo?.transcript || 'No transcript available.';
    el.readOnly = memoStatusForStep1 === 'pending_review'; // Editable only when pending_transcript
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

function _el(id) { return document.getElementById(id); }

function _isEmpty(v) {
  return v == null || v === '' || String(v).trim().toLowerCase() === 'unknown';
}

async function loadExtractionForEdit(memoId, dealId = null) {
  try {
    const memo = await api.getMemo(memoId);
    let ext = memo?.extraction || {};
    let raw = { ...(ext.raw_extraction || {}) };

    if (dealId) {
      let ctx = null;
      try {
        ctx = await chrome.runtime.sendMessage({ type: 'GET_DEAL_CONTEXT', dealId });
      } catch (_) { /* ignore */ }
      if (!ctx || ctx.error) {
        try {
          const preview = await chrome.runtime.sendMessage({ type: 'GET_PREVIEW', memoId, dealId });
          if (preview && !preview.error && preview.selected_deal) {
            const sel = preview.selected_deal;
            ctx = {
              companyName: sel.company_name || null,
              contactName: sel.contact_name || null,
              contactEmail: sel.contact_email || null,
              raw_extraction: { dealname: sel.deal_name, amount: sel.amount }
            };
            (preview.proposed_updates || []).forEach(u => {
              if (u.current_value && ctx.raw_extraction) {
                if (u.field_name === 'dealname') ctx.raw_extraction.dealname = u.current_value;
                else if (u.field_name === 'amount') ctx.raw_extraction.amount = parseFloat(u.current_value) || u.current_value;
                else if (u.field_name === 'closedate') ctx.raw_extraction.closedate = u.current_value;
                else if (u.field_name === 'dealstage') ctx.raw_extraction.dealstage = u.current_value;
                else if (u.field_name === 'hs_next_step') ctx.raw_extraction.hs_next_step = u.current_value;
                else if (u.field_name === 'company_name') ctx.companyName = ctx.companyName || u.current_value;
                else if (u.field_name === 'contact_name') ctx.contactName = ctx.contactName || u.current_value;
              }
            });
          }
        } catch (_) { /* ignore */ }
      }
      if (ctx && !ctx.error) {
        if (_isEmpty(ext.companyName) && ctx.companyName) {
          ext = { ...ext, companyName: ctx.companyName };
          raw.dealname = ctx.companyName;
        }
        if (_isEmpty(ext.contactName) && ctx.contactName) ext = { ...ext, contactName: ctx.contactName };
        if (_isEmpty(ext.contactEmail) && ctx.contactEmail) ext = { ...ext, contactEmail: ctx.contactEmail };
        const r = ctx.raw_extraction || {};
        if (_isEmpty(raw.dealname) && r.dealname) raw.dealname = r.dealname;
        if ((raw.amount == null || _isEmpty(raw.amount)) && r.amount != null) raw.amount = r.amount;
        if (_isEmpty(raw.closedate) && r.closedate) raw.closedate = r.closedate;
        if (_isEmpty(raw.dealstage) && r.dealstage) raw.dealstage = r.dealstage;
        if (_isEmpty(raw.hs_next_step) && r.hs_next_step) raw.hs_next_step = r.hs_next_step;
        ext = { ...ext, raw_extraction: raw };
      }
    }

    const nextSteps = Array.isArray(ext.nextSteps) ? ext.nextSteps : [];
    const nextStepsStr = nextSteps.map(s => `• ${s}`).join('\n');

    _el('ext-company').value = ext.companyName || raw.dealname || '';
    _el('ext-amount').value = ext.dealAmount != null ? String(ext.dealAmount) : (raw.amount != null ? String(raw.amount) : '');
    _el('ext-contact').value = ext.contactName || '';
    _el('ext-contact-email').value = ext.contactEmail || '';
    _el('ext-stage').value = ext.dealStage || raw.dealstage || '';
    _el('ext-closedate').value = ext.closeDate || raw.closedate || '';
    _el('ext-ftes').value = raw.deal_ftes_active != null ? String(raw.deal_ftes_active) : (raw.ftes_fulltime_employees != null ? String(raw.ftes_fulltime_employees) : '');
    _el('ext-price-per-fte').value = raw.price_per_fte_eur != null ? String(raw.price_per_fte_eur) : '';
    _el('ext-competitor-price').value = raw.competitor_price != null ? String(raw.competitor_price) : '';
    _el('ext-es-hi').value = raw.es_hi_provider || '';
    _el('ext-total-employees').value = raw.total_employees != null ? String(raw.total_employees) : '';
    _el('ext-priority').value = raw.hs_priority || '';
    _el('ext-summary').value = ext.summary || '';
    _el('ext-nextsteps').value = nextStepsStr;
    editedExtraction = ext;
  } catch (e) {
    console.error('[Popup] Failed to load extraction:', e);
  }
}

function collectEditedExtraction() {
  const parseBullets = (txt) => (txt || '').split('\n').map(l => l.replace(/^[•\-*]\s*/, '').trim()).filter(Boolean);
  const raw = { ...(editedExtraction?.raw_extraction || {}) };

  const company = _el('ext-company')?.value?.trim() || null;
  const amountStr = _el('ext-amount')?.value?.trim();
  const amount = amountStr ? parseFloat(amountStr) || null : null;
  const nextSteps = parseBullets(_el('ext-nextsteps')?.value || '');
  const ftesStr = _el('ext-ftes')?.value?.trim();
  const ftes = ftesStr ? parseFloat(ftesStr) || null : null;
  const pricePerFteStr = _el('ext-price-per-fte')?.value?.trim();
  const pricePerFte = pricePerFteStr ? parseFloat(pricePerFteStr) || null : null;
  const competitorPriceStr = _el('ext-competitor-price')?.value?.trim();
  const competitorPrice = competitorPriceStr ? parseFloat(competitorPriceStr) || null : null;
  const totalEmployeesStr = _el('ext-total-employees')?.value?.trim();
  const totalEmployees = totalEmployeesStr ? parseFloat(totalEmployeesStr) || null : null;

  if (company) raw.dealname = company;
  if (amount != null) raw.amount = amount;
  if (_el('ext-stage')?.value) raw.dealstage = _el('ext-stage').value;
  if (_el('ext-closedate')?.value) raw.closedate = _el('ext-closedate').value;
  if (ftes != null) { raw.deal_ftes_active = ftes; raw.ftes_fulltime_employees = ftes; }
  if (pricePerFte != null) raw.price_per_fte_eur = pricePerFte;
  if (competitorPrice != null) raw.competitor_price = competitorPrice;
  if (_el('ext-es-hi')?.value) raw.es_hi_provider = _el('ext-es-hi').value.trim();
  if (totalEmployees != null) raw.total_employees = totalEmployees;
  if (_el('ext-priority')?.value) raw.hs_priority = _el('ext-priority').value;
  if (nextSteps[0]) raw.hs_next_step = nextSteps[0];

  return {
    ...editedExtraction,
    companyName: company,
    dealAmount: amount,
    contactName: _el('ext-contact')?.value?.trim() || null,
    contactEmail: _el('ext-contact-email')?.value?.trim() || null,
    dealStage: _el('ext-stage')?.value || null,
    closeDate: _el('ext-closedate')?.value || null,
    summary: _el('ext-summary')?.value?.trim() || '',
    nextSteps,
    raw_extraction: raw
  };
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
  console.log('[Popup] Loading preview for memo:', memoId, 'dealId:', dealId, 'hasExtraction:', !!extraction);
  
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
    
    console.log('[Popup] Preview response:', preview);

    if (preview && !preview.error) {
      previewLoaded = true;
      const match = preview.selected_deal;
      currentDealId = match ? match.deal_id : null;

      // Transcript for review
      const transcriptEl = document.getElementById('transcript-content');
      if (transcriptEl) {
        transcriptEl.textContent = preview.transcript || preview.transcript_summary || 'No transcript available.';
      }
      
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
          const hadExisting =
            update.current_value != null &&
            String(update.current_value).trim() !== '' &&
            String(update.current_value).trim() !== '(empty)';
          const isOverride = !!hadExisting;
          div.className = 'update-item' + (isOverride ? ' override' : ' new');
          div.innerHTML = `
            <p class="update-label">${update.field_label || update.field_name}</p>
            <p class="update-value">${update.new_value || '—'}</p>
            ${hadExisting ? `<p class="update-current">Was: ${update.current_value}</p>` : ''}
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
          currentDealId = deal.deal_id;
          loadPreview(currentMemoId, deal.deal_id, editedExtraction);
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
      isNewDeal: !currentDealId,
      extraction: editedExtraction || undefined
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

// Review wizard - event delegation
document.getElementById('screen-review')?.addEventListener('click', async (e) => {
  if (e.target.id === 'review-continue-btn') {
    if (memoStatusForStep1 === 'pending_transcript') {
      // User confirmed transcript -> trigger extraction, poll until done, then step 2
      const transcriptEl = document.getElementById('transcript-content');
      const transcript = transcriptEl?.value?.trim() || '';
      if (!transcript) return;
      e.target.disabled = true;
      e.target.textContent = 'Extracting...';
      try {
        await api.post(`/memos/${currentMemoId}/confirm-transcript`, { transcript });
        setProcessingScreenMode('extracting');
        showScreen('processing');

        // Poll until pending_review (max ~2 min)
        let pollCount = 0;
        let done = false;
        while (pollCount < 60) {
          await new Promise(r => setTimeout(r, 2000));
          const memo = await api.getMemo(currentMemoId);
          if (memo.status === 'pending_review') {
            reviewStep = 2;
            memoStatusForStep1 = 'pending_review';
            hideExtractionError();
            showScreen('review');
            loadExtractionForEdit(currentMemoId);
            setReviewUIForStep(2);
            done = true;
            break;
          }
          if (memo.status === 'failed') {
            showExtractionError(memo.errorMessage || 'Extraction failed.');
            showScreen('review');
            loadTranscriptForReview(currentMemoId);
            setReviewUIForStep(1);
            done = true;
            break;
          }
          pollCount++;
        }
        if (!done && pollCount >= 60) {
          showExtractionError('Extraction is taking longer than expected. Click Retry to try again.');
          showScreen('review');
          loadTranscriptForReview(currentMemoId);
          setReviewUIForStep(1);
        }
      } catch (err) {
        console.error('[Popup] Confirm transcript error:', err);
        showExtractionError(err?.message || 'Something went wrong. Click Retry to try again.');
        showScreen('review');
        loadTranscriptForReview(currentMemoId);
        setReviewUIForStep(1);
      } finally {
        e.target.disabled = false;
        e.target.textContent = 'Continue to Step 2';
      }
    } else {
      // Already extracted (pending_review) - just go to step 2
      reviewStep = 2;
      chrome.runtime.sendMessage({ type: 'GET_STATE' }).then(s => renderState(s));
    }
  } else if (e.target.id === 'review-continue-step2-btn') {
    editedExtraction = collectEditedExtraction();
    reviewStep = 3;
    previewLoaded = false;
    api.getCurrentUser().catch(() => {}).finally(() => {
      chrome.runtime.sendMessage({ type: 'GET_STATE' }).then(s => renderState(s));
    });
  } else if (e.target.id === 'retry-extraction-btn') {
    e.target.disabled = true;
    e.target.textContent = 'Retrying...';
    hideExtractionError();
    setProcessingScreenMode('extracting');
    showScreen('processing');
    try {
      const memo = await api.reExtract(currentMemoId);
        if (memo?.status === 'pending_review' && memo?.extraction) {
        reviewStep = 2;
        memoStatusForStep1 = 'pending_review';
        hideExtractionError();
        showScreen('review');
        const st = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
        const dealId = st?.context?.objectType === 'deal' ? st.context.recordId : null;
        loadExtractionForEdit(currentMemoId, dealId);
        setReviewUIForStep(2);
      } else {
        showExtractionError(memo?.errorMessage || 'Retry failed.');
        showScreen('review');
        loadTranscriptForReview(currentMemoId);
        setReviewUIForStep(1);
      }
    } catch (err) {
      showExtractionError(err?.message || 'Retry failed. Try again.');
      showScreen('review');
      loadTranscriptForReview(currentMemoId);
      setReviewUIForStep(1);
    } finally {
      e.target.disabled = false;
      e.target.textContent = 'Retry extraction';
    }
  } else if (e.target.id === 'review-back-to-step1-btn') {
    reviewStep = 1;
    chrome.runtime.sendMessage({ type: 'GET_STATE' }).then(s => renderState(s));
  } else if (e.target.id === 'review-back-to-step2-btn') {
    reviewStep = 2;
    chrome.runtime.sendMessage({ type: 'GET_STATE' }).then(s => renderState(s));
  } else if (e.target.id === 'review-discard-btn' || e.target.id === 'review-discard-btn2') {
    chrome.runtime.sendMessage({ type: 'DISCARD_MEMO' });
  } else if (e.target.id === 'btn-use-current-deal') {
    chrome.runtime.sendMessage({ type: 'GET_STATE' }).then(state => {
      const dealId = state.context?.objectType === 'deal' ? state.context.recordId : null;
      if (dealId) {
        currentDealId = dealId;
        previewLoaded = false;
        loadPreview(currentMemoId, dealId, editedExtraction);
      }
    });
  }
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
    document.getElementById('user-name').textContent = user.full_name || 'User';
    document.getElementById('user-email').textContent = user.email;
    
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
