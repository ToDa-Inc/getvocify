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
let currentContactId = null;
let currentCompanyId = null;
/** Latest background state (includes HubSpot page context) */
let lastBgState = null;
/** Mirror dashboard HubSpotSyncPreview confidence gate */
const CONFIDENT_MATCH_THRESHOLD = 0.7;
/** When true, user must explicitly pick/create a deal before approve */
let needsDealDecision = false;
let dealDecisionMade = true;
/** Force create-new-deal on next/current preview */
let createNewDealRequested = false;
let searchTimeout = null;
let previewLoaded = false;
let sessionHeartbeatId = null;
/** Cached preview data for extraction merge */
let lastPreviewData = null;
/** Edits/removals from proposed updates (index → update or null if removed) */
let editedProposedUpdates = null;
/** Action items for HubSpot tasks: { id, text, checked } */
let reviewActionItems = [];
let actionItemIdSeq = 0;
/** Call outcome (optional): 'converted' | 'on_hold' | 'lost' | null */
let selectedCallOutcome = null;
/** Lost reason text actually sent to the backend - resolved from the select
 * (or the "Other" free-text input when '__other__' is chosen) */
let selectedLostReason = '';
/** Click-outside handler for Add field dropdown */
let addFieldCloseHandler = null;
/** Avoid re-fetching recent memos on every STATE_UPDATED while watching */
let recentMemosLoaded = false;
let recentMemosInFlight = false;
let lastRenderedStatus = null;
/** Cache key: deal:<id> | contact:<id> | global */
let recentMemosScopeKey = null;

function getRecentMemosScope(context) {
  if (context?.objectType === 'deal' && context?.recordId) {
    return { key: `deal:${context.recordId}`, dealId: context.recordId, contactId: null, label: 'Memos for this deal' };
  }
  if (context?.objectType === 'contact' && context?.recordId) {
    return { key: `contact:${context.recordId}`, dealId: null, contactId: context.recordId, label: 'Memos for this contact' };
  }
  return { key: 'global', dealId: null, contactId: null, label: 'Recent Memos' };
}

function isCrmDateField(u) {
  if (!u || !u.field_name) return false;
  const n = String(u.field_name).toLowerCase();
  const t = String(u.field_type || "").toLowerCase();
  if (n.includes("closedate") || n === "closed_date") return true;
  if (t === "number" || t === "currency") return false;
  if (t === "date" || t === "datetime") return true;
  return false;
}

/** Align with web app crm-date.ts: output YYYY-MM-DD for APIs. */
function parseFlexibleDateToIso(input) {
  if (input == null) return null;
  const s = String(input).trim();
  if (!s) return null;
  const head = s.slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(head)) {
    const d = new Date(head + "T12:00:00");
    return Number.isNaN(d.getTime()) ? null : head;
  }
  const m = s.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
  if (m) {
    const a = parseInt(m[1], 10);
    const b = parseInt(m[2], 10);
    const y = parseInt(m[3], 10);
    const dmy = new Date(y, b - 1, a);
    if (dmy.getFullYear() === y && dmy.getMonth() === b - 1 && dmy.getDate() === a) {
      return `${y}-${String(b).padStart(2, "0")}-${String(a).padStart(2, "0")}`;
    }
    const mdy = new Date(y, a - 1, b);
    if (mdy.getFullYear() === y && mdy.getMonth() === a - 1 && mdy.getDate() === b) {
      return `${y}-${String(a).padStart(2, "0")}-${String(b).padStart(2, "0")}`;
    }
  }
  return null;
}

function formatCrmDateDisplay(raw) {
  const iso = parseFlexibleDateToIso(raw);
  if (!iso) return raw && String(raw).trim() ? String(raw) : "";
  const parts = iso.split("-").map((x) => parseInt(x, 10));
  const dt = new Date(parts[0], parts[1] - 1, parts[2]);
  return dt.toLocaleDateString(undefined, { dateStyle: "long" });
}

// ============================================
// SCREEN MANAGEMENT
// ============================================
function showScreen(screenKey) {
  if (screenKey !== 'processing' && _processingAnimTimer) {
    clearInterval(_processingAnimTimer);
    _processingAnimTimer = null;
  }
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

let _processingAnimTimer = null;

const HUBSPOT_CALL_MESSAGES = [
  { title: 'HubSpot recording found. Transcribing…', msg: 'Converting speech to text with speaker detection.' },
  { title: 'Identifying speakers…', msg: 'Separating rep and prospect voices.' },
  { title: 'Analyzing the conversation…', msg: 'Preparing your transcript for review.' },
  { title: 'Almost there…', msg: 'Your call will be ready to review shortly.' },
];

const WATCH_STATUS_COPY = {
  awaiting_recording: 'Waiting for HubSpot to attach a recording…',
  awaiting_next: 'Recordings on this page — pick one to continue',
  ready: 'Recordings ready — tap Transcribe or Continue',
  new_recording: 'New recording available — tap Transcribe',
};

function isWatchableHubSpotContext(context) {
  return context?.recordId && ['deal', 'contact'].includes(context.objectType);
}

function getRecordDisplayName(context) {
  if (!context?.recordId) return null;
  if (context.objectType === 'deal') return context.dealName || 'Deal on this page';
  if (context.objectType === 'contact') return context.contactName || 'Contact on this page';
  if (context.objectType === 'company') return context.companyName || 'Company on this page';
  return null;
}

function formatCallTimestamp(ts) {
  if (!ts) return 'Unknown date';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return 'Unknown date';
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatCallDuration(seconds) {
  const s = Number(seconds);
  if (!s || s <= 0) return '';
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m > 0 ? `${m}m ${r}s` : `${r}s`;
}

function getMemoStatusPill(rec) {
  const st = rec.memo_status;
  if (!rec.memo_id) return null;
  if (st === 'approved') return { class: 'status-approved', text: 'Synced' };
  if (st === 'failed') return { class: 'status-failed', text: 'Failed' };
  if (st === 'pending_review' || st === 'pending_transcript') return { class: 'status-pending', text: 'Review' };
  if (['transcribing', 'uploading', 'extracting'].includes(st)) {
    return { class: 'status-processing', text: 'Processing' };
  }
  return { class: 'status-processing', text: (st || 'processing').replace(/_/g, ' ') };
}

function getRecordingAction(rec) {
  if (!rec.has_recording) return null;
  const st = rec.memo_status;
  if (!rec.memo_id || st === 'failed') return { label: 'Transcribe', action: 'transcribe' };
  if (['transcribing', 'uploading', 'extracting'].includes(st)) {
    return { label: 'Processing', action: 'none', disabled: true };
  }
  if (st === 'pending_transcript' || st === 'pending_review') {
    return { label: 'Continue', action: 'continue', memoId: rec.memo_id };
  }
  if (st === 'approved') return { label: 'View', action: 'view', memoId: rec.memo_id };
  if (st === 'rejected') return { label: 'Transcribe', action: 'transcribe' };
  return { label: 'Transcribe', action: 'transcribe' };
}

function renderRecordContextStrip(state) {
  const strip = document.getElementById('record-context-strip');
  const typeEl = document.getElementById('record-context-type');
  const nameEl = document.getElementById('record-context-name');
  if (!strip) return;

  const name = getRecordDisplayName(state.context);
  const show = !!name && (state.status === 'idle' || state.isRecording);
  strip.style.display = show ? 'flex' : 'none';
  if (!show) return;

  if (typeEl) {
    const labels = { contact: 'Contact', company: 'Company', deal: 'Deal' };
    typeEl.textContent = labels[state.context.objectType] || 'Record';
  }
  if (nameEl) nameEl.textContent = name;
}

function renderReviewRecordName(context) {
  const el = document.getElementById('review-record-name');
  if (!el) return;
  const name = getRecordDisplayName(context);
  if (name) {
    el.textContent = name;
    el.style.display = 'block';
  } else {
    el.textContent = '';
    el.style.display = 'none';
  }
}

function renderRecordingsSection(state) {
  const section = document.getElementById('recordings-section');
  const listEl = document.getElementById('recordings-list');
  const statusEl = document.getElementById('recordings-status-line');
  const dotEl = document.getElementById('recordings-watch-dot');
  if (!section) return;

  const show = isWatchableHubSpotContext(state.context) && state.status === 'idle';
  section.style.display = show ? 'block' : 'none';
  if (!show) return;

  if (statusEl) {
    if (state.recordingsLoading && !(state.recordings || []).some((r) => r.has_recording)) {
      statusEl.textContent = 'Loading recordings…';
    } else if (state.watchingForRecording) {
      statusEl.textContent = WATCH_STATUS_COPY[state.watchPhase] || WATCH_STATUS_COPY.awaiting_recording;
    } else {
      statusEl.textContent = 'Call recordings on this record';
    }
  }
  if (dotEl) {
    dotEl.style.display = state.watchingForRecording ? 'inline-block' : 'none';
  }
  const stopBtn = document.getElementById('recordings-stop-watch');
  if (stopBtn) stopBtn.style.display = state.watchingForRecording ? '' : 'none';

  const recordings = (state.recordings || []).filter((r) => r.has_recording);
  if (!listEl) return;

  if (state.recordingsLoading && !recordings.length) {
    listEl.innerHTML = '<p class="body-muted recordings-empty">Loading…</p>';
    return;
  }
  if (!recordings.length) {
    listEl.innerHTML = '<p class="body-muted recordings-empty">No call recordings yet on this record.</p>';
    return;
  }

  listEl.innerHTML = '';
  recordings.forEach((rec) => {
    const row = document.createElement('div');
    row.className = 'recording-row';
    const action = getRecordingAction(rec);
    const pill = getMemoStatusPill(rec);
    const dateStr = formatCallTimestamp(rec.timestamp || rec.timestamp_ms);
    const durStr = formatCallDuration(rec.duration_seconds);
    const title = rec.title || 'Call';

    row.innerHTML = `
      <div class="recording-row-main">
        <span class="recording-row-title">${escapeHtml(title)}</span>
        <span class="recording-row-meta">${escapeHtml(dateStr)}${durStr ? ` · ${escapeHtml(durStr)}` : ''}</span>
      </div>
      <div class="recording-row-actions">
        ${pill ? `<span class="status-pill ${pill.class}">${escapeHtml(pill.text)}</span>` : ''}
        ${action && action.action !== 'none'
          ? `<button type="button" class="btn-recording-action" data-call-id="${escapeHtml(rec.call_id)}" data-action="${action.action}"${action.memoId ? ` data-memo-id="${escapeHtml(action.memoId)}"` : ''}>${escapeHtml(action.label)}</button>`
          : ''}
        ${action?.disabled ? '<span class="recording-processing-label">Processing…</span>' : ''}
      </div>
    `;
    listEl.appendChild(row);
  });

  listEl.querySelectorAll('.btn-recording-action').forEach((btn) => {
    btn.addEventListener('click', handleRecordingAction);
  });
}

async function handleRecordingAction(e) {
  const btn = e.currentTarget;
  const callId = btn.dataset.callId;
  const action = btn.dataset.action;
  const memoId = btn.dataset.memoId;
  if (!callId && !memoId) return;

  btn.disabled = true;
  try {
    if (action === 'transcribe' && callId) {
      const res = await chrome.runtime.sendMessage({ type: 'PROCESS_HUBSPOT_CALL', callId });
      if (res?.error) throw new Error(res.error);
      const s = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
      renderState(s);
    } else if ((action === 'continue' || action === 'view') && memoId) {
      await chrome.runtime.sendMessage({
        type: 'SET_STATE',
        state: { status: 'review', currentMemoId: memoId },
      });
      const s = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
      renderState(s);
    }
  } catch (err) {
    console.error('[Popup] recording action error:', err);
    btn.disabled = false;
  }
}

/** Set processing screen text: 'transcribing' | 'extracting' | 'hubspot_call' */
function setProcessingScreenMode(mode) {
  if (_processingAnimTimer) { clearInterval(_processingAnimTimer); _processingAnimTimer = null; }

  const sub = document.getElementById('processing-subtitle');
  const title = document.getElementById('processing-title');
  const msg = document.getElementById('processing-message');

  if (mode === 'extracting') {
    if (sub) sub.textContent = 'Extracting';
    if (title) title.textContent = 'AI is analyzing your transcript...';
    if (msg) msg.textContent = 'Extracting CRM fields. Ready in a moment.';
  } else if (mode === 'hubspot_call') {
    if (sub) sub.textContent = 'Processing Call';
    let idx = 0;
    const update = () => {
      const m = HUBSPOT_CALL_MESSAGES[idx % HUBSPOT_CALL_MESSAGES.length];
      if (title) title.textContent = m.title;
      if (msg) msg.textContent = m.msg;
      idx++;
    };
    update();
    _processingAnimTimer = setInterval(update, 3000);
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
  lastBgState = state && typeof state === 'object' ? state : lastBgState;
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
    if (dealContextBadge) dealContextBadge.style.display = 'none';
    renderRecordContextStrip(state);

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
      {
        const pt = document.getElementById('processing-title');
        const pm = document.getElementById('processing-message');
        if (pt) pt.textContent = 'Converting speech to text...';
        if (pm) pm.textContent = 'Your transcript will be ready to review in a moment.';
      }
      
      // Ensure all idle elements are visible
      if (shortcutBox) {
        shortcutBox.style.display = 'block';
        shortcutBox.classList.toggle('shortcut-box--muted', isWatchableHubSpotContext(state.context));
      }
      if (recentMemos) recentMemos.style.display = 'block';
      if (pasteToggle) pasteToggle.style.display = 'flex';
      if (mainActions) mainActions.style.display = 'flex';
      if (pasteSection) pasteSection.style.display = 'none';

      previewLoaded = false;
      currentMemoId = null;
      renderRecordContextStrip(state);
      renderRecordingsSection(state);
      const scope = getRecentMemosScope(state.context);
      const scopeChanged = scope.key !== recentMemosScopeKey;
      if (scopeChanged) {
        recentMemosScopeKey = scope.key;
        recentMemosLoaded = false;
      }
      if (lastRenderedStatus !== 'idle' || !recentMemosLoaded || scopeChanged) {
        loadRecentMemos(scope);
      }
      break;
      
    case 'processing':
      setProcessingScreenMode(state.processingSource === 'hubspot_call' ? 'hubspot_call' : 'transcribing');
      showScreen('processing');
      break;
      
    case 'review':
      showScreen('review');
      renderReviewRecordName(state.context);
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
  lastRenderedStatus = state.status;
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
    const stepLabel = document.getElementById('review-step-label');
    const reviewScreen = document.getElementById('screen-review');

    if (pendingTranscript) {
      if (pendingSection) pendingSection.style.display = 'flex';
      if (proposedMain) proposedMain.style.display = 'none';
      if (reviewActions) reviewActions.style.display = 'none';
      if (stepLabel) stepLabel.textContent = 'Review transcript';
      if (reviewScreen) reviewScreen.classList.add('review-mode-transcript');
      renderReviewRecordName(context);
      syncTranscriptModalDeal(context);
      loadTranscriptForReview(memoId);
    } else {
      if (pendingSection) pendingSection.style.display = 'none';
      if (proposedMain) proposedMain.style.display = 'block';
      if (reviewActions) reviewActions.style.display = 'flex';
      if (stepLabel) stepLabel.textContent = 'Review & sync';
      if (reviewScreen) reviewScreen.classList.remove('review-mode-transcript');
      renderReviewRecordName(context);
      const onDealPage = context?.objectType === 'deal' && context?.recordId;
      const onContactPage = context?.objectType === 'contact' && context?.recordId;
      const onCompanyPage = context?.objectType === 'company' && context?.recordId;
      let dealIdToLoad = onDealPage ? context.recordId : currentDealId;
      let contactIdToLoad = onContactPage
        ? context.recordId
        : (context?.contactId || currentContactId || null);
      if (onCompanyPage) {
        currentCompanyId = context.recordId;
        let companyCtx = context;
        if (!context.companyName || !Array.isArray(context.companyContacts)) {
          try {
            const fetched = await chrome.runtime.sendMessage({
              type: 'GET_COMPANY_CONTEXT',
              companyId: context.recordId,
            });
            if (fetched && !fetched.error) {
              companyCtx = {
                ...context,
                companyName: fetched.companyName,
                companyId: context.recordId,
                contactId: fetched.contactId,
                companyContacts: fetched.contacts || [],
              };
              lastBgState = { ...(lastBgState || {}), context: companyCtx };
              context = companyCtx;
            }
          } catch (_) { /* keep raw context */ }
        }
        if (companyCtx.contactId) contactIdToLoad = companyCtx.contactId;
        else if (Array.isArray(companyCtx.companyContacts) && companyCtx.companyContacts.length === 1) {
          contactIdToLoad = companyCtx.companyContacts[0].contact_id;
        }
      }
      if (
        !previewLoaded ||
        currentMemoId !== memoId ||
        (onDealPage && currentDealId !== context?.recordId) ||
        (onContactPage && currentContactId !== context?.recordId) ||
        (onCompanyPage && currentCompanyId !== context?.recordId)
      ) {
        currentMemoId = memoId;
        if (onDealPage) currentDealId = context.recordId;
        previewLoaded = true;
        // Company with multiple contacts and no preferred: show picker first
        if (
          onCompanyPage &&
          !contactIdToLoad &&
          Array.isArray(context.companyContacts) &&
          context.companyContacts.length > 1
        ) {
          renderContactTarget({ selected_contact: null, contact_candidates: [] });
          if (approveSyncButton) {
            approveSyncButton.disabled = true;
            approveSyncButton.textContent = 'Confirm Contact First';
          }
        } else {
          let extractionOverride = null;
          if (onCompanyPage && !contactIdToLoad && context.companyName) {
            try {
              const memoFull = await api.getMemo(memoId);
              const base = memoFull?.extraction && typeof memoFull.extraction === 'object'
                ? { ...memoFull.extraction }
                : {};
              base.companyName = context.companyName;
              extractionOverride = base;
            } catch (_) { /* optional */ }
          }
          await loadPreview(memoId, dealIdToLoad, extractionOverride, contactIdToLoad);
        }
      }
      showUsePageRecordOption(context);
      const preview = lastPreviewData;
      const tx = preview?.transcript || memo?.transcript || '';
      renderTranscriptConversation(tx, {
        editable: false,
        container: document.getElementById('review-transcript-conversation'),
      });
      const noteCb = document.getElementById('create-note-checkbox');
      const noteRow = document.getElementById('create-note-row');
      if (noteCb) {
        noteCb.checked = !!tx.trim();
        noteCb.disabled = !tx.trim();
      }
      if (noteRow) noteRow.classList.toggle('is-disabled', !tx.trim());
    }
  } catch (e) {
    console.error('[Popup] handleReviewState error:', e);
  }
}

function syncTranscriptModalDeal(context) {
  const el = document.getElementById('transcript-modal-deal');
  if (!el) return;
  const name = getRecordDisplayName(context);
  if (name) {
    el.textContent = name;
    el.style.display = 'inline-flex';
  } else {
    el.textContent = '';
    el.style.display = 'none';
  }
}

function speakerLabel(raw) {
  const s = String(raw || '').trim().toUpperCase();
  if (s === 'S1' || s === 'SPEAKER 1' || s === 'SPEAKER1') return 'Speaker 1';
  if (s === 'S2' || s === 'SPEAKER 2' || s === 'SPEAKER2') return 'Speaker 2';
  if (/^S\d+$/i.test(s)) return `Speaker ${s.slice(1)}`;
  return raw || 'Speaker';
}

function speakerSide(raw) {
  const s = String(raw || '').trim().toUpperCase();
  if (s === 'S1' || s === 'SPEAKER 1' || s === 'SPEAKER1') return 's1';
  if (s === 'S2' || s === 'SPEAKER 2' || s === 'SPEAKER2') return 's2';
  if (/^S1\b/i.test(s)) return 's1';
  if (/^S2\b/i.test(s)) return 's2';
  return 'other';
}

/**
 * Parse Speechmatics-style "SPEAKER: S1\\n..." transcripts into conversation turns.
 */
function parseTranscriptTurns(text) {
  const raw = String(text || '').trim();
  if (!raw) return [];

  const lines = raw.split(/\r?\n/);
  const turns = [];
  let current = null;

  const speakerRe = /^(?:SPEAKER:\s*)?(S\d+|Speaker\s*\d+)\s*:?\s*$/i;
  const inlineRe = /^(?:SPEAKER:\s*)?(S\d+|Speaker\s*\d+)\s*[:.-]\s*(.+)$/i;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (current) current.text += '\n';
      continue;
    }
    const inline = trimmed.match(inlineRe);
    if (inline) {
      if (current && current.text.trim()) turns.push(current);
      current = { speaker: inline[1].replace(/\s+/g, ''), text: inline[2].trim() };
      continue;
    }
    const onlySpeaker = trimmed.match(speakerRe);
    if (onlySpeaker) {
      if (current && current.text.trim()) turns.push(current);
      current = { speaker: onlySpeaker[1].replace(/\s+/g, ''), text: '' };
      continue;
    }
    if (!current) current = { speaker: null, text: trimmed };
    else current.text = current.text ? `${current.text}\n${trimmed}` : trimmed;
  }
  if (current && (current.text.trim() || current.speaker)) turns.push(current);

  // Fallback: no speaker markers — one block
  if (!turns.length && raw) return [{ speaker: null, text: raw }];
  return turns.map((t) => ({ ...t, text: t.text.replace(/\n+$/g, '').trim() })).filter((t) => t.text);
}

function serializeTranscriptTurns(container) {
  const turns = [...(container?.querySelectorAll('.transcript-turn') || [])];
  if (!turns.length) {
    return document.getElementById('transcript-content')?.value?.trim() || '';
  }
  return turns.map((turn) => {
    const speaker = turn.dataset.speaker;
    const bubble = turn.querySelector('.transcript-bubble');
    const text = (bubble?.innerText || bubble?.textContent || '').trim();
    if (!text) return '';
    if (speaker) return `SPEAKER: ${speaker}\n${text}`;
    return text;
  }).filter(Boolean).join('\n\n');
}

function syncTranscriptHiddenField() {
  const hidden = document.getElementById('transcript-content');
  const convo = document.getElementById('transcript-conversation');
  if (!hidden || !convo) return;
  hidden.value = serializeTranscriptTurns(convo);
}

function renderTranscriptConversation(text, { editable = true, container = null } = {}) {
  const convo = container || document.getElementById('transcript-conversation');
  const hidden = document.getElementById('transcript-content');
  // Always keep the hidden field in sync — Extract & Continue reads from it
  if (hidden && !container) hidden.value = text || '';

  if (!convo) return;

  const turns = parseTranscriptTurns(text);
  // Only write the editable step-1 hidden field when rendering into the main conversation
  if (hidden && !container) hidden.value = text || '';

  if (!turns.length) {
    convo.innerHTML = '<p class="transcript-empty">No transcript available.</p>';
    return;
  }

  convo.innerHTML = '';
  turns.forEach((turn) => {
    const side = speakerSide(turn.speaker);
    const row = document.createElement('div');
    row.className = `transcript-turn transcript-turn--${side}`;
    if (turn.speaker) {
      const m = String(turn.speaker).match(/(\d+)/);
      row.dataset.speaker = m ? `S${m[1]}` : String(turn.speaker).toUpperCase();
    }

    if (turn.speaker) {
      const label = document.createElement('span');
      label.className = 'transcript-speaker';
      label.textContent = speakerLabel(row.dataset.speaker || turn.speaker);
      row.appendChild(label);
    }

    const bubble = document.createElement('div');
    bubble.className = 'transcript-bubble';
    bubble.textContent = turn.text;
    if (editable) {
      bubble.contentEditable = 'true';
      bubble.spellcheck = true;
      bubble.addEventListener('input', syncTranscriptHiddenField);
      bubble.addEventListener('blur', syncTranscriptHiddenField);
    }
    row.appendChild(bubble);
    convo.appendChild(row);
  });
  if (editable && !container) syncTranscriptHiddenField();
}

/** Show "Use X on this page" for deal / contact / company HubSpot pages */
function showUsePageRecordOption(context) {
  const opt = document.getElementById('use-page-record-option');
  const btn = document.getElementById('btn-use-page-record');
  if (!opt || !btn) return;
  const type = context?.objectType;
  const ok = !!context?.recordId && ['deal', 'contact', 'company'].includes(type);
  opt.style.display = ok ? 'block' : 'none';
  if (!ok) return;
  const labels = {
    deal: 'Use deal on this page',
    contact: 'Use contact on this page',
    company: 'Use company on this page',
  };
  btn.textContent = labels[type] || 'Use record on this page';
}

async function loadTranscriptForReview(memoId) {
  const convo = document.getElementById('transcript-conversation');
  const hidden = document.getElementById('transcript-content');
  if (convo) convo.innerHTML = '<p class="transcript-empty">Loading transcript…</p>';
  if (hidden) {
    hidden.value = '';
    hidden.readOnly = true;
  }
  try {
    const memo = await api.getMemo(memoId);
    const status = memo?.status || '';
    const editable = status === 'pending_transcript';
    renderTranscriptConversation(memo?.transcript || '', { editable });
    if (hidden) hidden.readOnly = !editable;
    if (memo?.status === 'failed') {
      showExtractionError(memo?.errorMessage || 'Extraction failed. Click Retry to try again.');
    } else if (memo?.status === 'extracting') {
      showExtractionError('Extraction is still in progress or stuck. Click Retry to try again.');
    } else {
      hideExtractionError();
    }
  } catch (e) {
    console.error('[Popup] Failed to load transcript:', e);
    if (convo) convo.innerHTML = '<p class="transcript-empty">Failed to load transcript.</p>';
    if (hidden) {
      hidden.value = '';
      hidden.readOnly = true;
    }
  }
}

// ============================================
// PREVIEW & DEAL LOGIC
// ============================================
async function loadRecentMemos(scope) {
  const listElement = document.getElementById('recent-memos-list');
  const labelEl = document.getElementById('recent-memos-label');
  if (!listElement) return;
  if (recentMemosInFlight) return;
  recentMemosInFlight = true;

  const resolved = scope || getRecentMemosScope(null);
  if (labelEl) labelEl.textContent = resolved.label;

  try {
    const memos = await chrome.runtime.sendMessage({
      type: 'GET_RECENT_MEMOS',
      dealId: resolved.dealId || undefined,
      contactId: resolved.contactId || undefined,
    });
    
    if (memos && !memos.error && Array.isArray(memos)) {
      recentMemosLoaded = true;
      if (memos.length === 0) {
        const empty = resolved.key === 'global'
          ? 'No memos yet.'
          : 'No memos for this record yet.';
        listElement.innerHTML = `<p class="body-muted" style="text-align: center; padding: 10px;">${empty}</p>`;
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
        
        const isActionable = ['pending_review', 'pending_transcript', 'approved'].includes(memo.status);
        if (!isActionable) item.classList.add('not-actionable');

        item.onclick = () => {
          if (memo.status === 'pending_review' || memo.status === 'pending_transcript') {
            chrome.runtime.sendMessage({
              type: 'SET_STATE',
              state: { status: 'review', currentMemoId: memo.id },
            });
          } else if (memo.status === 'approved') {
            chrome.runtime.sendMessage({
              type: 'SET_STATE',
              state: { status: 'success', currentMemoId: memo.id, syncResult: memo },
            });
          }
        };
        listElement.appendChild(item);
      });
    }
  } catch (e) {
    console.error('[Popup] Failed to load recent memos:', e);
  } finally {
    recentMemosInFlight = false;
  }
}

async function loadPreview(memoId, dealId = null, extraction = null, contactId = null, opts = null) {
  document.getElementById('target-deal-name').textContent = 'Loading...';
  document.getElementById('target-deal-reason').textContent = '';
  proposedUpdatesList.innerHTML = '<div class="spinner" style="margin: 20px auto;"></div>';

  const createNewDeal = !!(opts && opts.createNewDeal) || createNewDealRequested;
  if (createNewDeal) createNewDealRequested = true;

  // Prefer explicit contact, then page context contact
  const ctx = lastBgState?.context;
  const pageContactId =
    contactId ||
    (ctx?.objectType === 'contact' ? ctx.recordId : null) ||
    ctx?.contactId ||
    currentContactId ||
    null;

  try {
    const preview = await chrome.runtime.sendMessage({
      type: 'GET_PREVIEW',
      memoId,
      dealId: createNewDeal ? null : dealId,
      contactId: pageContactId || undefined,
      createNewDeal: createNewDeal || undefined,
      extraction: extraction || undefined
    });

    if (preview && !preview.error) {
      lastPreviewData = preview;
      previewLoaded = true;
      const match = preview.selected_deal;
      currentDealId = match ? match.deal_id : null;
      currentContactId = preview.selected_contact?.contact_id || pageContactId || null;
      currentCompanyId =
        preview.selected_contact?.company_id ||
        currentCompanyId ||
        lastBgState?.context?.companyId ||
        (lastBgState?.context?.objectType === 'company' ? lastBgState.context.recordId : null) ||
        null;

      renderContactTarget(preview);

      const skipDeal = !!preview.skip_deal && !match;
      document.getElementById('target-deal-name').textContent = match
        ? match.deal_name
        : skipDeal
          ? 'Contact only (no deal)'
          : (createNewDeal || preview.is_new_deal ? 'New Deal' : 'No deal selected');
      const reasonText = match
        ? (match.match_reason === 'Manual Selection' ? 'From current page' : `Matched via ${(match.match_reason || 'AI').toLowerCase()}`)
        : skipDeal
          ? 'Sync will update the matched contact'
          : (createNewDeal || preview.is_new_deal
            ? 'A new record will be created'
            : 'Choose a deal or create a new one');
      document.getElementById('target-deal-reason').textContent = reasonText;

      const dealLabel = document.getElementById('deal-target-label');
      const changeBtn = document.getElementById('btn-change-deal');
      if (dealLabel) {
        dealLabel.textContent = preview.selected_contact ? 'Deal Target (optional)' : 'Deal Target';
      }
      if (changeBtn) {
        changeBtn.textContent = preview.selected_contact ? 'Choose Deal' : 'Change Deal';
      }

      // Reset edited state when loading fresh preview
      editedProposedUpdates = null;
      initCallInsights(preview);
      try {
        const memo = await api.getMemo(memoId);
        const summaryEl = document.getElementById('review-summary');
        if (summaryEl && !summaryEl.value.trim() && memo?.extraction?.summary) {
          summaryEl.value = memo.extraction.summary;
        }
        if (!reviewActionItems.length && Array.isArray(memo?.extraction?.nextSteps)) {
          reviewActionItems = memo.extraction.nextSteps
            .filter((s) => s && String(s).trim())
            .map((text) => ({ id: ++actionItemIdSeq, text: String(text).trim(), checked: true }));
          renderActionItems();
        }
      } catch (_) { /* optional enrichment */ }

      const decision = evaluateDealDecision(preview, { createNewDeal });
      if (decision.autoSelectDealId && !createNewDeal) {
        createNewDealRequested = false;
        await loadPreview(memoId, decision.autoSelectDealId, null, pageContactId);
        return;
      }
      renderDealDecisionUI(preview);
      updateApproveButtonState(preview);
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

/**
 * Mirror dashboard HubSpotSyncPreview init:
 * - ambiguous contacts → wait for contact pick
 * - contact locked → deal optional (skip_deal OK)
 * - no contact → confident deal auto-select, else force confirm
 */
function evaluateDealDecision(preview, { createNewDeal = false } = {}) {
  const selectedContact = preview?.selected_contact;
  const candidates = Array.isArray(preview?.contact_candidates) ? preview.contact_candidates : [];
  const matches = Array.isArray(preview?.matched_deals) ? preview.matched_deals : [];
  const selectedDeal = preview?.selected_deal;

  if (candidates.length > 0 && !selectedContact) {
    needsDealDecision = false;
    dealDecisionMade = false;
    return {};
  }
  if (selectedContact) {
    needsDealDecision = false;
    dealDecisionMade = true;
    return {};
  }
  if (selectedDeal || createNewDeal) {
    needsDealDecision = false;
    dealDecisionMade = true;
    return {};
  }
  const top = matches[0];
  const confident = !!top && (top.match_confidence ?? 0) >= CONFIDENT_MATCH_THRESHOLD;
  if (confident && top.deal_id) {
    return { autoSelectDealId: top.deal_id };
  }
  needsDealDecision = true;
  dealDecisionMade = false;
  return {};
}

function updateApproveButtonState(preview) {
  if (!approveSyncButton) return;
  const candidates = Array.isArray(preview?.contact_candidates) ? preview.contact_candidates : [];
  const needsContactPick = !preview?.selected_contact && candidates.length > 0;
  if (needsContactPick) {
    approveSyncButton.disabled = true;
    approveSyncButton.textContent = 'Confirm Contact First';
    return;
  }
  if (needsDealDecision && !dealDecisionMade) {
    approveSyncButton.disabled = true;
    approveSyncButton.textContent = 'Confirm Deal Target First';
    return;
  }
  // Mirrors the backend's own validation (ApproveMemoRequest._lost_requires_reason,
  // a 422 if violated) - this is UX only, the server is the real enforcement.
  if (selectedCallOutcome === 'lost' && !getEffectiveLostReason()) {
    approveSyncButton.disabled = true;
    approveSyncButton.textContent = 'Add a Lost Reason';
    return;
  }

  approveSyncButton.disabled = false;
  const skipDeal = !!preview?.skip_deal && !preview?.selected_deal;
  if (skipDeal && preview?.selected_contact) {
    approveSyncButton.textContent = `Update ${preview.selected_contact.name || preview.selected_contact.email || 'Contact'}`;
  } else if (preview?.selected_deal) {
    approveSyncButton.textContent = `Update ${preview.selected_deal.deal_name}`;
  } else {
    approveSyncButton.textContent = 'Confirm & Update CRM';
  }
}

function renderDealDecisionUI(preview) {
  const box = document.getElementById('deal-decision-box');
  const list = document.getElementById('matched-deals-list');
  const card = document.getElementById('deal-card');
  const hint = document.getElementById('deal-decision-hint');
  if (!box || !list) return;

  const selectedContact = preview?.selected_contact;
  const matches = Array.isArray(preview?.matched_deals) ? preview.matched_deals : [];
  const skipDeal = !!preview?.skip_deal && !preview?.selected_deal;
  const showWeakConfirm = needsDealDecision && !dealDecisionMade;
  const showLinkedDeals = !!selectedContact && skipDeal && matches.length > 0 && !createNewDealRequested;

  if (!showWeakConfirm && !showLinkedDeals) {
    box.style.display = 'none';
    list.innerHTML = '';
    if (card) card.style.display = 'block';
    return;
  }

  box.style.display = 'block';
  if (card && showWeakConfirm) card.style.display = 'none';
  else if (card) card.style.display = 'block';

  if (hint) {
    hint.textContent = showWeakConfirm
      ? "We couldn't confidently match this memo to a deal. Choose one below or create a new deal."
      : 'Linked deals available — pick one or keep contact-only sync.';
  }

  list.innerHTML = '';
  matches.slice(0, 5).forEach((m) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'matched-deal-item';
    btn.innerHTML = `<strong>${escapeHtml(m.deal_name || 'Deal')}</strong><br><span class="deal-subtitle">${escapeHtml(m.match_reason || '')}</span>`;
    btn.addEventListener('click', () => selectDealTarget(m.deal_id));
    list.appendChild(btn);
  });
}

function selectDealTarget(dealId) {
  createNewDealRequested = false;
  needsDealDecision = false;
  dealDecisionMade = true;
  previewLoaded = false;
  currentDealId = dealId;
  loadPreview(currentMemoId, dealId, null, currentContactId);
}

function createNewDealTarget() {
  createNewDealRequested = true;
  needsDealDecision = false;
  dealDecisionMade = true;
  previewLoaded = false;
  currentDealId = null;
  const searchBox = document.getElementById('deal-search-box');
  if (searchBox) searchBox.style.display = 'none';
  loadPreview(currentMemoId, null, null, currentContactId, { createNewDeal: true });
}

function renderContactTarget(preview) {
  const section = document.getElementById('contact-target-section');
  const candidatesEl = document.getElementById('contact-candidates');
  const nameEl = document.getElementById('target-contact-name');
  const metaEl = document.getElementById('target-contact-meta');
  const card = document.getElementById('contact-card');
  if (!section) return;

  const selected = preview?.selected_contact;
  const candidates = Array.isArray(preview?.contact_candidates) ? preview.contact_candidates : [];
  const pageCompanyContacts =
    lastBgState?.context?.objectType === 'company' && Array.isArray(lastBgState.context.companyContacts)
      ? lastBgState.context.companyContacts
      : [];
  const companyPickList =
    !selected && !candidates.length && pageCompanyContacts.length > 1 ? pageCompanyContacts : [];

  if (!selected && !candidates.length && !companyPickList.length) {
    section.style.display = 'none';
    return;
  }
  section.style.display = 'block';

  if (selected) {
    if (card) card.style.display = 'block';
    if (nameEl) nameEl.textContent = selected.name || selected.email || 'Contact';
    const bits = [selected.email, selected.phone, selected.company_name, selected.match_reason]
      .filter(Boolean);
    if (metaEl) metaEl.textContent = bits.join(' · ');
    if (candidatesEl) {
      candidatesEl.style.display = 'none';
      candidatesEl.innerHTML = '';
    }
    return;
  }

  if (card) card.style.display = 'none';
  const pick = candidates.length ? candidates : companyPickList;
  if (candidatesEl) {
    candidatesEl.style.display = 'block';
    candidatesEl.innerHTML = '';
    const hint = document.createElement('p');
    hint.className = 'deal-subtitle';
    hint.style.margin = '0 0 8px';
    hint.textContent = candidates.length
      ? 'Multiple contacts matched — pick one:'
      : 'Multiple contacts on this company — pick one:';
    candidatesEl.appendChild(hint);
    pick.forEach((c) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'matched-deal-item';
      btn.innerHTML = `<strong>${escapeHtml(c.name || 'Contact')}</strong><br><span class="deal-subtitle">${escapeHtml([c.email, c.phone, c.company_name].filter(Boolean).join(' · '))}</span>`;
      btn.addEventListener('click', () => {
        currentContactId = c.contact_id;
        loadPreview(currentMemoId, currentDealId, null, c.contact_id);
      });
      candidatesEl.appendChild(btn);
    });
  }
}

function isInsightsField(fieldName) {
  return (
    fieldName === 'description' ||
    fieldName === 'hs_next_step' ||
    String(fieldName || '').startsWith('next_step_task_')
  );
}

function initCallInsights(preview) {
  const updates = preview?.proposed_updates || [];
  const summaryEl = document.getElementById('review-summary');
  const desc = updates.find((u) => u?.field_name === 'description');
  const summaryText =
    (desc?.new_value && String(desc.new_value).trim()) ||
    preview?.transcript_summary ||
    '';
  if (summaryEl) summaryEl.value = summaryText;

  const steps = [];
  updates.forEach((u) => {
    if (!u) return;
    if (u.field_name?.startsWith('next_step_task_') || u.field_name === 'hs_next_step') {
      const text = String(u.new_value || '').trim();
      if (text) steps.push({ id: ++actionItemIdSeq, text, checked: true });
    }
  });
  // Dedupe identical strings
  const seen = new Set();
  reviewActionItems = steps.filter((s) => {
    const key = s.text.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  renderActionItems();
  initCallOutcome(preview);
}

// ============================================
// CALL OUTCOME (Converted / On Hold / Lost)
// ============================================

/** Reset to the neutral "no outcome picked" state for a freshly loaded preview. */
function initCallOutcome(preview) {
  selectedCallOutcome = null;
  selectedLostReason = '';

  // Per-outcome gate (backend/app/services/hubspot/call_outcome.py -
  // compute_call_outcome_availability): Converted needs no per-account
  // setup, but On Hold / Lost each only appear once the admin has mapped
  // one of their OWN hs_lead_status values to that outcome (HubSpot
  // Configuration screen) - never show a button that would fail (or
  // no-op) after the rep clicks it, hide it instead of disabling it, so
  // there's nothing confusing to explain in the extension itself.
  const availability = preview?.call_outcome_availability || {};
  const showConverted = !!availability.converted;
  const showOnHold = !!availability.on_hold;
  const showLost = !!availability.lost;

  const section = document.getElementById('call-outcome-section');
  if (section) section.style.display = (showConverted || showOnHold || showLost) ? '' : 'none';

  const convertedBtn = document.getElementById('outcome-btn-converted');
  if (convertedBtn) convertedBtn.style.display = showConverted ? '' : 'none';
  const onHoldBtn = document.getElementById('outcome-btn-on_hold');
  if (onHoldBtn) onHoldBtn.style.display = showOnHold ? '' : 'none';
  const lostBtn = document.getElementById('outcome-btn-lost');
  if (lostBtn) lostBtn.style.display = showLost ? '' : 'none';

  if (showLost) {
    const select = document.getElementById('lost-reason-select');
    const otherInput = document.getElementById('lost-reason-other-input');
    if (select) {
      const reasons = Array.isArray(preview?.lost_reasons) ? preview.lost_reasons : [];
      select.innerHTML = '<option value="">Select a reason…</option>' +
        reasons.map((r) => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`).join('') +
        '<option value="__other__">Other…</option>';
      select.value = '';
    }
    if (otherInput) {
      otherInput.value = '';
      otherInput.style.display = 'none';
    }
  }
  renderCallOutcome();
}

function getEffectiveLostReason() {
  const select = document.getElementById('lost-reason-select');
  const otherInput = document.getElementById('lost-reason-other-input');
  if (!select) return '';
  if (select.value === '__other__') return (otherInput?.value || '').trim();
  return select.value || '';
}

function renderCallOutcome() {
  ['converted', 'on_hold', 'lost'].forEach((outcome) => {
    const btn = document.getElementById(`outcome-btn-${outcome}`);
    if (btn) btn.classList.toggle('is-active', selectedCallOutcome === outcome);
  });
  const lostBox = document.getElementById('lost-reason-box');
  if (lostBox) lostBox.style.display = selectedCallOutcome === 'lost' ? 'flex' : 'none';

  const hint = document.getElementById('lost-reason-hint');
  if (hint) {
    const satisfied = selectedCallOutcome !== 'lost' || !!getEffectiveLostReason();
    hint.classList.toggle('is-satisfied', satisfied);
    hint.textContent = satisfied
      ? 'Reason saved.'
      : 'A reason is required to mark this call as Lost.';
  }
  updateApproveButtonState(lastPreviewData);
}

document.getElementById('call-outcome-buttons')?.addEventListener('click', (e) => {
  const btn = e.target.closest('.outcome-btn');
  if (!btn) return;
  const outcome = btn.dataset.outcome;
  // Clicking the already-active outcome deselects it - outcome is optional,
  // a rep should be able to change their mind without a page reload.
  selectedCallOutcome = selectedCallOutcome === outcome ? null : outcome;
  if (selectedCallOutcome !== 'lost') selectedLostReason = '';
  renderCallOutcome();
});

document.getElementById('lost-reason-select')?.addEventListener('change', (e) => {
  const otherInput = document.getElementById('lost-reason-other-input');
  const isOther = e.target.value === '__other__';
  if (otherInput) {
    otherInput.style.display = isOther ? 'block' : 'none';
    if (isOther) otherInput.focus();
  }
  selectedLostReason = getEffectiveLostReason();
  renderCallOutcome();
});

document.getElementById('lost-reason-other-input')?.addEventListener('input', () => {
  selectedLostReason = getEffectiveLostReason();
  renderCallOutcome();
});

function renderActionItems() {
  const list = document.getElementById('action-items-list');
  const empty = document.getElementById('action-items-empty');
  if (!list) return;
  list.innerHTML = '';

  if (!reviewActionItems.length) {
    if (empty) empty.style.display = 'block';
    return;
  }
  if (empty) empty.style.display = 'none';

  reviewActionItems.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'action-item' + (item.checked ? '' : ' is-unchecked');
    row.dataset.id = String(item.id);
    row.innerHTML = `
      <label class="action-item-check">
        <input type="checkbox" ${item.checked ? 'checked' : ''} data-action="toggle">
        <span class="action-item-box" aria-hidden="true"></span>
      </label>
      <input type="text" class="action-item-text" value="${escapeHtml(item.text)}" data-action="edit">
      <button type="button" class="action-item-remove" data-action="remove" title="Remove">×</button>
    `;
    const checkbox = row.querySelector('input[type="checkbox"]');
    const textInput = row.querySelector('.action-item-text');
    const removeBtn = row.querySelector('[data-action="remove"]');

    checkbox?.addEventListener('change', () => {
      item.checked = !!checkbox.checked;
      row.classList.toggle('is-unchecked', !item.checked);
    });
    textInput?.addEventListener('input', () => {
      item.text = textInput.value;
    });
    removeBtn?.addEventListener('click', () => {
      reviewActionItems = reviewActionItems.filter((x) => x.id !== item.id);
      renderActionItems();
    });
    list.appendChild(row);
  });
}

function addActionItem(text = '') {
  reviewActionItems.push({ id: ++actionItemIdSeq, text: text || '', checked: true });
  renderActionItems();
  const list = document.getElementById('action-items-list');
  const last = list?.querySelector('.action-item:last-child .action-item-text');
  last?.focus();
}

function renderProposedUpdates(updates, availableFields) {
  proposedUpdatesList.innerHTML = '';
  const list = editedProposedUpdates !== null ? editedProposedUpdates : updates.map((u) => ({ ...u }));
  // Insights (summary / tasks) live in dedicated sections — keep out of deal field list
  const filteredList = list.filter(
    (u) =>
      u &&
      !['contact_name', 'company_name', 'dealname'].includes(u.field_name) &&
      !isInsightsField(u.field_name)
  );

  if (!filteredList.length) {
    proposedUpdatesList.innerHTML =
      '<p class="body-muted" style="padding: 8px 4px;">No field updates proposed for this call.</p>';
  }

  filteredList.forEach((update, idx) => {
      if (!update) return; // removed
      // Map back to original index in editedProposedUpdates / updates for edit/remove
      const sourceList = editedProposedUpdates !== null ? editedProposedUpdates : updates;
      const realIdx = sourceList.findIndex((u) => u === update || (u && update && u.field_name === update.field_name && u.new_value === update.new_value));
      const idxForEdit = realIdx >= 0 ? realIdx : idx;

      const hadExisting =
        update.current_value != null &&
        String(update.current_value).trim() !== '' &&
        String(update.current_value).trim() !== '(empty)';
      const isOverride = !!hadExisting;
      const isDealField =
        (update.object_type || 'deals') === 'deals' &&
        !String(update.field_name || '').startsWith('line_item_') &&
        !String(update.field_name || '').startsWith('next_step_task_');
      const objectLabel = ({
        deals: 'Deal',
        contacts: 'Contact',
        companies: 'Company',
        line_items: 'Line item',
        task: 'Task',
      })[update.object_type || 'deals'] || 'Deal';

      const editIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>`;
      const removeIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>`;

      const div = document.createElement('div');
      div.className = 'update-item' + (isOverride ? ' override' : ' new');
      div.dataset.idx = String(idxForEdit);
      div.innerHTML = `
        <div class="update-content">
          <div class="update-header-row">
            <div>
              <p class="update-object-type">${objectLabel}</p>
              <p class="update-label">${update.field_label || update.field_name}</p>
            </div>
            ${isDealField ? `
              <div class="update-actions">
                <button class="update-action-btn edit" title="Edit">${editIcon}</button>
                <button class="update-action-btn remove" title="Remove">${removeIcon}</button>
              </div>
            ` : ''}
          </div>
          <p class="update-value">${escapeHtml(isCrmDateField(update) ? (formatCrmDateDisplay(update.new_value) || update.new_value || '—') : (update.new_value || '—'))}</p>
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
          ` : `<input type="${update.field_type === 'number' ? 'number' : isCrmDateField(update) ? 'date' : 'text'}" class="update-edit-input" value="${escapeHtml(parseFlexibleDateToIso(update.new_value) || '')}" style="display:none;" />`}
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
          editInput.value = isCrmDateField(update)
            ? (parseFlexibleDateToIso(update.new_value) || '')
            : (update.new_value || '');
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
          if (customTrigger) customTrigger.textContent = label;
          update.new_value = v;
          if (editedProposedUpdates === null) {
            editedProposedUpdates = (lastPreviewData?.proposed_updates || []).map((u) => (u ? { ...u } : null));
          }
          const i = Number(div.dataset.idx);
          if (editedProposedUpdates[i]) editedProposedUpdates[i] = { ...editedProposedUpdates[i], new_value: v };
          closeCustomSelect();
          valueEl.style.display = '';
          valueEl.textContent = label || '—';
          if (customSelectWrapper) customSelectWrapper.style.display = 'none';
          div.classList.remove('editing');
        };
      });
    }
    if (editInput && editInput.tagName === 'INPUT') {
      editInput.onblur = () => {
        const v = editInput.value;
        update.new_value = v;
        if (editedProposedUpdates === null) {
          editedProposedUpdates = (lastPreviewData?.proposed_updates || []).map((u) => (u ? { ...u } : null));
        }
        const i = Number(div.dataset.idx);
        if (editedProposedUpdates[i]) editedProposedUpdates[i] = { ...editedProposedUpdates[i], new_value: v };
        valueEl.style.display = '';
        valueEl.textContent = isCrmDateField(update)
          ? (formatCrmDateDisplay(v) || v || '—')
          : (v || '—');
        editInput.style.display = 'none';
        div.classList.remove('editing');
      };
      editInput.onkeydown = (e) => {
        if (e.key === 'Enter') editInput.blur();
      };
    }
    if (removeBtn) {
      removeBtn.onclick = () => {
        if (editedProposedUpdates === null) {
          editedProposedUpdates = (lastPreviewData?.proposed_updates || []).map((u) => (u ? { ...u } : null));
        }
        const i = Number(div.dataset.idx);
        editedProposedUpdates[i] = null;
        renderProposedUpdates(editedProposedUpdates.filter(Boolean), availableFields);
      };
    }

    proposedUpdatesList.appendChild(div);
  });

  // Keep Add field working — available fields still exclude insights handled above
  const addBtn = document.getElementById('btn-add-field');
  const dropdown = document.getElementById('add-field-dropdown');
  const sourceForAdd = editedProposedUpdates !== null ? editedProposedUpdates : updates;
  const remaining = (availableFields || []).filter(
    (f) => f?.name && !sourceForAdd.some((u) => u && u.field_name === f.name) && !isInsightsField(f.name)
  );
  if (remaining.length > 0 && addBtn) {
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
        dropdown.innerHTML = remaining
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
            const nextList = editedProposedUpdates !== null
              ? [...editedProposedUpdates.filter(Boolean), newUpdate]
              : [...updates.map((u) => (u ? { ...u } : null)).filter(Boolean), newUpdate];
            editedProposedUpdates = nextList;
            if (addFieldCloseHandler) {
              document.removeEventListener('click', addFieldCloseHandler);
              addFieldCloseHandler = null;
            }
            dropdown.style.display = 'none';
            renderProposedUpdates(editedProposedUpdates, availableFields);
          };
        });
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
    };
  } else if (addBtn) {
    addBtn.style.display = 'none';
    if (dropdown) dropdown.style.display = 'none';
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
  const contactProps = { ...((raw.contact_properties && typeof raw.contact_properties === 'object') ? raw.contact_properties : {}) };
  const companyProps = { ...((raw.company_properties && typeof raw.company_properties === 'object') ? raw.company_properties : {}) };

  const updates = editedProposedUpdates !== null
    ? editedProposedUpdates.filter(Boolean)
    : (preview.proposed_updates || []);

  for (const u of updates) {
    if (isInsightsField(u.field_name)) continue; // handled below from dedicated UI
    const val = u.new_value?.trim() || null;
    if (!val) continue;
    const objectType = u.object_type || 'deals';

    if (objectType === 'contacts' && u.field_name !== 'contact_name') {
      contactProps[u.field_name] = u.field_type === 'number' ? (parseFloat(val) || null) : val;
      continue;
    }
    if (objectType === 'companies' && u.field_name !== 'company_name') {
      companyProps[u.field_name] = u.field_type === 'number' ? (parseFloat(val) || null) : val;
      continue;
    }
    if (objectType === 'line_items' || String(u.field_name || '').startsWith('line_item_')) {
      continue;
    }

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
    } else if (u.field_name === 'closedate' || u.field_name === 'CloseDate') {
      const iso = parseFlexibleDateToIso(val) || val;
      base.closeDate = iso;
      raw.closedate = iso;
      raw.CloseDate = iso;
    } else if (u.field_name === 'dealstage') {
      base.dealStage = val;
      raw.dealstage = val;
    } else if (val) {
      if (u.field_type === 'number') {
        raw[u.field_name] = parseFloat(val) || null;
      } else if (u.field_type === 'date' || u.field_type === 'datetime') {
        raw[u.field_name] = parseFlexibleDateToIso(val) || val;
      } else {
        raw[u.field_name] = val;
      }
    }
  }

  if (Object.keys(contactProps).length) raw.contact_properties = contactProps;
  if (Object.keys(companyProps).length) raw.company_properties = companyProps;

  // Summary + action items from dedicated review sections (Option A)
  const summaryEl = document.getElementById('review-summary');
  const summary = (summaryEl?.value || '').trim();
  base.summary = summary;
  raw.description = summary;

  const selectedSteps = reviewActionItems
    .filter((i) => i.checked && (i.text || '').trim())
    .map((i) => i.text.trim());
  base.nextSteps = selectedSteps;
  if (selectedSteps[0]) raw.hs_next_step = selectedSteps[0];
  else delete raw.hs_next_step;

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
          createNewDealRequested = false;
          previewLoaded = false;
          currentDealId = deal.deal_id;
          loadPreview(currentMemoId, deal.deal_id, null, currentContactId);
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
  const titleEl = document.querySelector('#screen-success .title-large');
  const iconEl = document.querySelector('#screen-success .success-checkmark');
  const iconContainerEl = document.querySelector('#screen-success .success-icon-container');

  if (result && result.deal_url) {
    msg.textContent = `Updated "${result.deal_name || 'deal'}" in HubSpot.`;
    btn.href = result.deal_url;
    btn.style.display = 'block';
  } else {
    msg.textContent = 'CRM updated successfully!';
    btn.style.display = 'none';
  }

  // outcome_failed is CRITICAL: for Lost, the reason note itself (the one
  // guaranteed record - see call_outcome.py) wasn't saved anywhere - unlike
  // outcome_warning, this must not
  // look like plain success (a green check + "Sync Successful" would be
  // misleading about the one thing the rep just explicitly asked for).
  // The rest of the memo (deal/contact/notes) still synced fine, so this
  // swaps the headline/icon rather than blocking the screen entirely.
  const failedEl = document.getElementById('success-outcome-failed');
  const hasFailure = !!(result && result.outcome_failed);
  if (titleEl) titleEl.textContent = hasFailure ? 'Synced - outcome not saved' : 'Sync Successful';
  if (iconEl) iconEl.textContent = hasFailure ? '!' : '✓';
  if (iconContainerEl) iconContainerEl.classList.toggle('success-icon-container--warning', hasFailure);
  if (failedEl) {
    if (hasFailure) {
      failedEl.textContent = result.outcome_failed;
      failedEl.style.display = 'block';
    } else {
      failedEl.textContent = '';
      failedEl.style.display = 'none';
    }
  }

  // outcome_warning is MINOR: call_outcome was requested and the core
  // write succeeded, but a secondary mirror step (deal stage, follow-up
  // task) didn't - the sync still fully succeeded, this is just a
  // non-blocking heads-up under the normal success state.
  const warningEl = document.getElementById('success-outcome-warning');
  if (warningEl) {
    if (result && result.outcome_warning) {
      warningEl.textContent = result.outcome_warning;
      warningEl.style.display = 'block';
    } else {
      warningEl.textContent = '';
      warningEl.style.display = 'none';
    }
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

document.getElementById('btn-create-new-deal')?.addEventListener('click', () => createNewDealTarget());
document.getElementById('btn-create-new-deal-search')?.addEventListener('click', () => createNewDealTarget());

// Deal search input
dealSearchInput?.addEventListener('input', (e) => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => searchDeals(e.target.value), 300);
});

// Approve sync
approveSyncButton?.addEventListener('click', async () => {
  if (needsDealDecision && !dealDecisionMade) return;
  const candidates = Array.isArray(lastPreviewData?.contact_candidates) ? lastPreviewData.contact_candidates : [];
  if (!lastPreviewData?.selected_contact && candidates.length > 0) return;
  if (selectedCallOutcome === 'lost' && !getEffectiveLostReason()) return;

  approveSyncButton.disabled = true;
  approveSyncButton.textContent = 'Syncing...';
  hideExtractionError();

  try {
    const extraction = await buildExtractionForApprove();
    const createNote = document.getElementById('create-note-checkbox')?.checked !== false;
    const skipDeal = !!lastPreviewData?.skip_deal && !currentDealId && !createNewDealRequested;
    const response = await chrome.runtime.sendMessage({
      type: 'APPROVE_SYNC',
      memoId: currentMemoId,
      dealId: currentDealId,
      isNewDeal: (!!createNewDealRequested || (!currentDealId && !skipDeal)),
      extraction: extraction || undefined,
      createNote,
      contactId: currentContactId || lastPreviewData?.selected_contact?.contact_id || undefined,
      companyId: currentCompanyId || lastPreviewData?.selected_contact?.company_id || undefined,
      skipDeal,
      callOutcome: selectedCallOutcome || undefined,
      lostReason: selectedCallOutcome === 'lost' ? getEffectiveLostReason() : undefined,
    });
    // Background never rejects this message (it always calls sendResponse), so
    // a failed sync surfaces as response.error here, not as a thrown exception.
    if (response?.error) {
      showExtractionError(response.error);
    }
  } catch (e) {
    console.error('[Popup] Approve error:', e);
    showExtractionError(e?.message || 'Something went wrong. Please try again.');
  } finally {
    updateApproveButtonState(lastPreviewData);
  }
});

document.getElementById('btn-add-action-item')?.addEventListener('click', () => addActionItem(''));

document.getElementById('processing-cancel-button')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'DISCARD_MEMO' });
});

document.getElementById('recordings-stop-watch')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'STOP_CALL_WATCH' });
  chrome.runtime.sendMessage({ type: 'GET_STATE' }).then((s) => renderState(s));
});
document.getElementById('call-watch-stop')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'STOP_CALL_WATCH' });
  chrome.runtime.sendMessage({ type: 'GET_STATE' }).then((s) => renderState(s));
});

// Discard button (step 2)
document.getElementById('discard-button')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'DISCARD_MEMO' });
});

// Review - confirm transcript (Extract & Continue)
document.getElementById('review-confirm-transcript-btn')?.addEventListener('click', async function () {
  syncTranscriptHiddenField();
  const transcriptEl = document.getElementById('transcript-content');
  const transcript = transcriptEl?.value?.trim() || '';
  if (!transcript) {
    showExtractionError('Transcript is empty. Wait for it to load, or re-record.');
    return;
  }
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
        chrome.runtime.sendMessage({
          type: 'SET_STATE',
          state: { status: 'review', currentMemoId },
        });
        return;
      }
      if (memo.status === 'failed') {
        showExtractionError(memo.errorMessage || 'Extraction failed.');
        showScreen('review');
        handleReviewState(currentMemoId, lastBgState?.context || {});
        return;
      }
      pollCount++;
    }
    showExtractionError('Extraction is taking longer than expected. Click Retry to try again.');
    showScreen('review');
    handleReviewState(currentMemoId, lastBgState?.context || {});
  } catch (err) {
    showExtractionError(err?.message || 'Something went wrong. Click Retry to try again.');
    showScreen('review');
    handleReviewState(currentMemoId, lastBgState?.context || {});
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

// Use deal / contact / company from the active HubSpot page
document.getElementById('btn-use-page-record')?.addEventListener('click', async () => {
  const state = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
  const ctx = state?.context;
  if (!ctx?.recordId) return;

  createNewDealRequested = false;
  previewLoaded = false;

  if (ctx.objectType === 'deal') {
    currentDealId = ctx.recordId;
    await loadPreview(currentMemoId, ctx.recordId, null, ctx.contactId || currentContactId);
    return;
  }

  if (ctx.objectType === 'contact') {
    currentContactId = ctx.recordId;
    currentCompanyId = ctx.companyId || currentCompanyId;
    await loadPreview(currentMemoId, currentDealId, null, ctx.recordId);
    return;
  }

  if (ctx.objectType === 'company') {
    currentCompanyId = ctx.recordId;
    let companyCtx = ctx;
    if (!ctx.companyName && !Array.isArray(ctx.companyContacts)) {
      companyCtx = await chrome.runtime.sendMessage({
        type: 'GET_COMPANY_CONTEXT',
        companyId: ctx.recordId,
      });
      if (companyCtx && !companyCtx.error) {
        lastBgState = {
          ...(lastBgState || state),
          context: {
            ...ctx,
            companyName: companyCtx.companyName,
            companyId: ctx.recordId,
            contactId: companyCtx.contactId,
            companyContacts: companyCtx.contacts || [],
          },
        };
      }
    }
    const contacts = Array.isArray(companyCtx?.contacts)
      ? companyCtx.contacts
      : (Array.isArray(ctx.companyContacts) ? ctx.companyContacts : []);
    if (companyCtx?.contactId || contacts.length === 1) {
      const cid = companyCtx?.contactId || contacts[0].contact_id;
      currentContactId = cid;
      await loadPreview(currentMemoId, null, null, cid);
      return;
    }
    if (contacts.length > 1) {
      // Show company contacts as pick list via renderContactTarget path
      lastPreviewData = {
        ...(lastPreviewData || {}),
        selected_contact: null,
        contact_candidates: [],
        matched_deals: lastPreviewData?.matched_deals || [],
        skip_deal: false,
      };
      if (lastBgState?.context) {
        lastBgState.context.companyContacts = contacts;
      }
      renderContactTarget({ selected_contact: null, contact_candidates: [] });
      approveSyncButton.disabled = true;
      approveSyncButton.textContent = 'Confirm Contact First';
      return;
    }
    // Company with no contacts: stamp company name into extraction for identity cascade
    let extractionOverride = null;
    try {
      const memo = await api.getMemo(currentMemoId);
      const base = memo?.extraction && typeof memo.extraction === 'object' ? { ...memo.extraction } : {};
      base.companyName = companyCtx?.companyName || ctx.companyName || base.companyName;
      extractionOverride = base;
    } catch (_) { /* optional */ }
    await loadPreview(currentMemoId, null, extractionOverride, null);
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
    const nameEl = document.getElementById('user-name');
    if (nameEl) nameEl.textContent = user.full_name || 'User';
    const emailEl = document.getElementById('user-email');
    if (emailEl) emailEl.textContent = user.email;
    
    const state = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
    // Service worker may return undefined if the message channel closed before sendResponse
    renderState(state && typeof state === 'object' ? state : { status: 'idle', isRecording: false });
  } catch (e) {
    console.error('[Popup] Init error:', e);
    const msg = String(e?.message || '');
    const detail = typeof e?.data?.detail === 'string' ? e.data.detail : msg;
    const isAuthError =
      e?.status === 401 ||
      (e?.name === 'ApiError' && e?.status === 401) ||
      /session expired|unauthorized|401/i.test(msg);
    const isAuthPlatformError =
      e?.status === 503 ||
      /oauth_client_id|supabase auth|token refresh failed|platform bug/i.test(detail);
    const isNetworkError =
      msg === 'Failed to fetch' ||
      (/network|connection|refused|load failed/i.test(msg) && !isAuthPlatformError);

    if (isAuthError) {
      showScreen('login');
    } else if (isAuthPlatformError || isNetworkError) {
      document.getElementById('loading-spinner').style.display = 'none';
      document.getElementById('loading-backend-error').style.display = 'block';
      const titleEl = document.getElementById('loading-error-title');
      const detailEl = document.getElementById('loading-error-detail');
      if (isAuthPlatformError) {
        if (titleEl) titleEl.textContent = 'Could not restore your session.';
        if (detailEl) {
          detailEl.textContent = /oauth_client_id|platform bug|infrastructure/i.test(detail)
            ? 'Supabase Auth token refresh is broken on this project. Upgrade/restart infrastructure in the Supabase dashboard, then sign in again.'
            : (detail || 'Sign out and sign in again. If this keeps happening, check Supabase Auth.');
        }
      } else {
        if (titleEl) titleEl.textContent = 'Could not connect to the server.';
        if (detailEl) detailEl.textContent = 'Please check your internet connection and try again.';
      }
    } else {
      // Unknown error (e.g. render bug) — don't wipe session; show idle record screen
      showScreen('record');
      renderState({ status: 'idle', isRecording: false });
    }
  }
}

init();
