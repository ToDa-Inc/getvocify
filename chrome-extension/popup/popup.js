/**
 * Popup Script - Mini-Dashboard
 * 
 * Mirrors the dashboard UX in a compact popup format.
 */

import { api } from '../lib/api.js';
import { isAuthFailure, screenForInitFailure, shouldPaintMainUi } from '../lib/auth-session.js';
import { resolveReviewPresentation, sameMemoId } from '../lib/review-screen.js';
import { buildHubSpotUrl } from '../lib/hubspot-parser.js';
import {
  buildApproveExtraction,
  canEditOrRemoveProposedField,
  isInsightsField,
  proposedFieldKey,
} from '../lib/extraction-omit.js';
import { bindPreviewIds, formatSyncTargetLabel, needsAssociatedContactPick, associatedContactsFromContext, resolveReviewTargets } from '../lib/review-targets.js';
import { listenClickRuntimeMessage, listenUiModel, requestTabCaptureStreamId, resolveListenPhase } from '../lib/tab-capture.js';
import {
  firstName,
  normalizeDiarizedTranscript,
  parseTranscriptTurns,
  speakerDisplayLabel,
  speakerSide,
} from '../lib/transcript-turns.js';
import { callDurationSeconds, formatCallDuration } from '../lib/call-duration.js';
import { recordingsScopeKey } from '../lib/page-scope.js';
import {
  RECORDINGS_PAGE_SIZE,
  activityEmptyMessage,
  isRecordPageContext,
  nextVisibleCount,
  shouldFetchVocifyMemos,
  shouldShowInboxKicker,
} from '../lib/activity-list.js';

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
/** Explicit deal pick this review (search / linked-deal click). Not a leftover page. */
let userSelectedDealId = null;
/** Explicit contact pick this review (candidate / company picker). */
let userSelectedContactId = null;
/** `${objectType}:${recordId}` for the HubSpot page this review is scoped to */
let lastPageRecordKey = null;
/** Latest background state (includes HubSpot page context) */
let lastBgState = null;
/** Drops an in-flight Listen start if the user hits Stop before START_TAB_CAPTURE is sent */
let listenStartSeq = 0;
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
/** Field keys (`object_type:field_name`) binned for this approve only */
let omittedProposedKeys = new Set();
/** Action items for HubSpot tasks: { id, text, checked } */
let reviewActionItems = [];
let actionItemIdSeq = 0;
/** Call outcome (optional): 'converted' | 'on_hold' | 'lost' | null */
let selectedCallOutcome = null;
/** Lost reason text actually sent to the backend - resolved from the select
 * (or the "Other" free-text input when '__other__' is chosen) */
let selectedLostReason = '';
/** True after tasks were seeded or the user edited them this review */
let actionItemsInitialized = false;
/** Memo whose call note is currently in the textarea */
let insightsMemoId = null;
/** Click-outside handler for Add field dropdown */
let addFieldCloseHandler = null;
/** Avoid re-fetching recent memos on every STATE_UPDATED while watching */
let recentMemosLoaded = false;
let recentMemosFetchGen = 0;
let reviewFetchGen = 0;
let lastRenderedStatus = null;
/** Cache key: deal:<id> | contact:<id> | global */
let recentMemosScopeKey = null;
let idleContextPollId = null;
/** unknown until init() finishes; signed_out must never paint record/idle */
let authStatus = 'unknown';
let recordingsVisibleCount = RECORDINGS_PAGE_SIZE;
let lastRecordingsScopeKey = null;

function getRecentMemosScope(context) {
  if (context?.objectType === 'deal' && context?.recordId) {
    return { key: `deal:${context.recordId}`, dealId: context.recordId, contactId: null, skip: false };
  }
  if (context?.objectType === 'contact' && context?.recordId) {
    return { key: `contact:${context.recordId}`, dealId: null, contactId: context.recordId, skip: false };
  }
  if (isRecordPageContext(context) && context.objectType === 'company') {
    return { key: `company:${context.recordId}`, dealId: null, contactId: null, skip: true };
  }
  return { key: 'global', dealId: null, contactId: null, skip: false };
}

function isCurrentReviewMemo(memoId) {
  return sameMemoId(lastBgState?.currentMemoId, memoId);
}

function startIdleContextPoll() {
  if (authStatus !== 'signed_in') return;
  if (idleContextPollId) return;
  idleContextPollId = setInterval(() => {
    if (authStatus !== 'signed_in') return;
    if (lastBgState?.status !== 'idle' || lastBgState?.isRecording || lastBgState?.isCopilotListening) {
      return;
    }
    chrome.runtime.sendMessage({ type: 'GET_STATE' }).then((s) => {
      if (s && typeof s === 'object') renderState(s);
    }).catch(() => {});
  }, 800);
}

function enterLoggedOut() {
  authStatus = 'signed_out';
  stopIdleContextPoll();
  stopSessionHeartbeat();
  lastRenderedStatus = null;
  showScreen('login');
}

function markSignedIn() {
  authStatus = 'signed_in';
}

function stopIdleContextPoll() {
  if (!idleContextPollId) return;
  clearInterval(idleContextPollId);
  idleContextPollId = null;
}

function pageRecordKey(context) {
  if (!context?.objectType || !context?.recordId) return null;
  return `${context.objectType}:${context.recordId}`;
}

function syncPageRecordScope(context) {
  const key = pageRecordKey(context);
  if (key === lastPageRecordKey) return;
  lastPageRecordKey = key;
  lastPreviewData = null;
  previewLoaded = false;
  userSelectedDealId = null;
  userSelectedContactId = null;
  createNewDealRequested = false;
  currentDealId = null;
  currentContactId = null;
  currentCompanyId = context?.objectType === 'company' ? context.recordId : (context?.companyId || null);
}

function currentReviewTargets(context, extra = {}) {
  return resolveReviewTargets({
    pageContext: context || lastBgState?.context,
    userDealId: extra.userDealId !== undefined ? extra.userDealId : userSelectedDealId,
    userContactId: extra.userContactId !== undefined ? extra.userContactId : userSelectedContactId,
    createNewDeal: extra.createNewDeal !== undefined ? extra.createNewDeal : createNewDealRequested,
  });
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
  if (screenKey !== 'processing') stopProcessingElapsed();
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

let _processingElapsedTimer = null;
let _processingStartedAt = 0;

function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function stopProcessingElapsed() {
  if (_processingElapsedTimer) {
    clearInterval(_processingElapsedTimer);
    _processingElapsedTimer = null;
  }
  if (_processingCopyTimer) {
    clearInterval(_processingCopyTimer);
    _processingCopyTimer = null;
  }
  if (_processingCopyFade) {
    clearTimeout(_processingCopyFade);
    _processingCopyFade = null;
  }
}

const PROCESSING_COPY = {
  transcribing: [
    'Writing the call down…',
    'Sorting who said what…',
    'Cleaning up the audio…',
  ],
  extracting: [
    'Filling in the fields…',
    'Matching this to HubSpot…',
    'Almost ready to review…',
  ],
};

let _processingCopyTimer = null;
let _processingCopyFade = null;
let _processingCopyIdx = 0;

function startProcessingCopy(mode) {
  const lines = PROCESSING_COPY[mode] || PROCESSING_COPY.transcribing;
  const msg = document.getElementById('processing-message');
  if (_processingCopyFade) {
    clearTimeout(_processingCopyFade);
    _processingCopyFade = null;
  }
  _processingCopyIdx = 0;
  const tick = () => {
    if (!msg) return;
    msg.style.opacity = '0';
    _processingCopyFade = window.setTimeout(() => {
      msg.textContent = lines[_processingCopyIdx % lines.length];
      msg.style.opacity = '1';
      _processingCopyIdx += 1;
      _processingCopyFade = null;
    }, 180);
  };
  if (msg) {
    msg.style.opacity = '1';
    msg.textContent = lines[0];
    _processingCopyIdx = 1;
  }
  if (_processingCopyTimer) clearInterval(_processingCopyTimer);
  _processingCopyTimer = setInterval(tick, 2600);
}

function startProcessingElapsed(mode = 'transcribing') {
  stopProcessingElapsed();
  startProcessingCopy(mode);
  _processingStartedAt = Date.now();
  const el = document.getElementById('processing-elapsed');
  const tick = () => {
    if (el) el.textContent = formatElapsed(Date.now() - _processingStartedAt);
  };
  tick();
  _processingElapsedTimer = setInterval(tick, 1000);
}

function memoReadyInLabel(memo) {
  const start = Date.parse(memo?.createdAt || memo?.created_at || '');
  const end = Date.parse(memo?.processedAt || memo?.processed_at || '');
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return '';
  const sec = Math.round((end - start) / 1000);
  if (sec < 1) return '';
  if (sec < 60) return `Ready in ${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return s ? `Ready in ${m}m ${s}s` : `Ready in ${m}m`;
}

const WATCH_STATUS_COPY = {
  awaiting_recording: 'Watching for a recording…',
  awaiting_next: 'HubSpot calls',
  ready: 'HubSpot calls',
  new_recording: 'New recording',
};

function isMacPlatform() {
  const platform = navigator.userAgentData?.platform || navigator.platform || '';
  return /mac/i.test(platform);
}

function fillShortcutHint() {
  const el = document.getElementById('shortcut-box');
  if (!el || el.dataset.filled === '1') return;
  el.dataset.filled = '1';
  el.innerHTML = isMacPlatform()
    ? '<kbd class="kbd">⌥</kbd><kbd class="kbd">⇧</kbd><kbd class="kbd">V</kbd>'
    : '<kbd class="kbd">Alt</kbd><kbd class="kbd">Shift</kbd><kbd class="kbd">V</kbd>';
}

function getRecordTypeLabel(context) {
  if (!context?.recordId) return '';
  if (context.objectType === 'deal') return 'Deal';
  if (context.objectType === 'contact') return 'Contact';
  if (context.objectType === 'company') return 'Company';
  return 'Record';
}

function renderRecordHeader(state) {
  const kicker = document.getElementById('record-header-kicker');
  const sub = document.getElementById('record-header-subtitle');
  const type = getRecordTypeLabel(state.context);
  if (kicker) kicker.textContent = type;
  if (recordButton && !state.isRecording) {
    const tip = type
      ? `Record a voice memo for this ${type.toLowerCase()}`
      : 'Record a voice memo';
    recordButton.setAttribute('data-tip', tip);
    recordButton.setAttribute('aria-label', tip);
  }
  if (!sub) return;
  if (state.isCopilotListening || state.status === 'copilot') {
    sub.textContent = state.copilotTabTitle || getRecordDisplayName(state.context) || '';
    return;
  }
  sub.textContent = getRecordDisplayName(state.context) || '';
}

function setIdleListsHidden() {
  const wrap = document.getElementById('record-activity');
  const recordings = document.getElementById('recordings-section');
  const memos = document.getElementById('recent-memos-section');
  const empty = document.getElementById('activity-empty');
  const kicker = document.getElementById('recordings-inbox-kicker');
  const showMore = document.getElementById('recordings-show-more');
  if (wrap) wrap.style.display = 'none';
  if (recordings) recordings.style.display = 'none';
  if (memos) memos.style.display = 'none';
  if (empty) empty.style.display = 'none';
  if (kicker) kicker.style.display = 'none';
  if (showMore) showMore.style.display = 'none';
}

function hubspotCallMemoIds(state) {
  return new Set(
    (state?.recordings || []).map((r) => r.memo_id).filter(Boolean).map(String)
  );
}

function isVocifyMemo(memo, callIds) {
  const id = memo?.id != null ? String(memo.id) : '';
  if (id && callIds.has(id)) return false;
  const src = memo?.source || memo?.source_type;
  if (src === 'hubspot_call') return false;
  if (memo?.hubspot_engagement_id) return false;
  return true;
}

function visibleMemoCount() {
  const list = document.getElementById('recent-memos-list');
  if (!list) return 0;
  return list.querySelectorAll('.memo-item').length;
}

function syncActivityEmptyState(state) {
  const emptyEl = document.getElementById('activity-empty');
  if (!emptyEl) {
    syncRecordActivityVisibility();
    return;
  }
  if (state?.status !== 'idle') {
    emptyEl.style.display = 'none';
    emptyEl.textContent = '';
    syncRecordActivityVisibility();
    return;
  }
  if (state.recordingsError) {
    emptyEl.textContent = state.recordingsError;
    emptyEl.style.display = 'block';
    syncRecordActivityVisibility();
    return;
  }
  const recordings = (state.recordings || []).filter((r) => r.has_recording);
  const memosLoading = shouldFetchVocifyMemos(state.context) && !recentMemosLoaded;
  const msg = activityEmptyMessage(state.context, {
    recordingsCount: recordings.length,
    memosCount: visibleMemoCount(),
    loading: Boolean(state.recordingsLoading || memosLoading),
  });
  if (msg) {
    emptyEl.textContent = msg;
    emptyEl.style.display = 'block';
  } else {
    emptyEl.textContent = '';
    emptyEl.style.display = 'none';
  }
  syncRecordActivityVisibility();
}

function syncRecordActivityVisibility() {
  const wrap = document.getElementById('record-activity');
  const rec = document.getElementById('recordings-section');
  const memos = document.getElementById('recent-memos-section');
  const empty = document.getElementById('activity-empty');
  if (!wrap) return;
  const recOn = rec && rec.style.display !== 'none';
  const memosOn = memos && memos.style.display !== 'none';
  const emptyOn = empty && empty.style.display !== 'none';
  wrap.style.display = recOn || memosOn || emptyOn ? 'block' : 'none';
}

function pruneCallMemosFromList(state) {
  const callIds = hubspotCallMemoIds(state || lastBgState);
  const list = document.getElementById('recent-memos-list');
  const section = document.getElementById('recent-memos-section');
  if (!list) return;
  list.querySelectorAll('.memo-item').forEach((el) => {
    const id = el.dataset.memoId;
    if (id && callIds.has(id)) el.remove();
  });
  if (section && !list.querySelector('.memo-item')) section.style.display = 'none';
  syncActivityEmptyState(state || lastBgState);
}

function getRecordDisplayName(context) {
  if (!context?.recordId) return null;
  if (context.objectType === 'deal') return context.dealName || null;
  if (context.objectType === 'contact') return context.contactName || null;
  if (context.objectType === 'company') return context.companyName || null;
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

function memoBusyLabel(status) {
  if (status === 'uploading') return 'Uploading';
  if (status === 'extracting') return 'Extracting';
  if (status === 'transcribing') return 'Transcribing';
  return null;
}

function getMemoStatusPill(rec) {
  const st = rec.memo_status;
  if (!rec.memo_id) return null;
  const busy = memoBusyLabel(st);
  if (busy) return { class: 'status-processing', text: busy, busy: true };
  if (st === 'approved') return { class: 'status-approved', text: 'Synced' };
  if (st === 'failed') return { class: 'status-failed', text: 'Failed' };
  if (st === 'pending_review' || st === 'pending_transcript') return { class: 'status-pending', text: 'Review' };
  return { class: 'status-processing', text: (st || 'processing').replace(/_/g, ' ') };
}

function getRecordingAction(rec) {
  if (!rec.has_recording) return null;
  const st = rec.memo_status;
  if (memoBusyLabel(st)) return null;
  if (!rec.memo_id || st === 'failed' || st === 'rejected') return { label: 'Transcribe', action: 'transcribe' };
  if (st === 'pending_transcript' || st === 'pending_review') {
    return { label: 'Continue', action: 'continue', memoId: rec.memo_id };
  }
  if (st === 'approved') return { label: 'View', action: 'view', memoId: rec.memo_id };
  return { label: 'Transcribe', action: 'transcribe' };
}

function busyStatusHtml(label) {
  return `<span class="status-busy"><span class="mini-spinner" aria-hidden="true"></span>${escapeHtml(label)}</span>`;
}

function renderRecordContextStrip(state) {
  const strip = document.getElementById('record-context-strip');
  if (strip) strip.style.display = 'none';
  renderRecordHeader(state);
}

function renderReviewRecordName(context, preview = lastPreviewData) {
  const el = document.getElementById('review-record-name');
  if (!el) return;
  const targets = currentReviewTargets(context);
  const needsPick = needsAssociatedContactPick(context, targets.contactId);
  const contactName =
    preview?.selected_contact?.name ||
    preview?.selected_contact?.email ||
    context?.contactName ||
    (context?.objectType === 'contact' ? getRecordDisplayName(context) : null);
  const dealName = targets.skipDeal
    ? null
    : (preview?.selected_deal?.deal_name ||
      context?.dealName ||
      (context?.objectType === 'deal' ? getRecordDisplayName(context) : null));
  const label = formatSyncTargetLabel({
    contactName,
    dealName,
    skipDeal: targets.skipDeal,
    needsContactPick: needsPick,
  });
  if (label) {
    el.textContent = label;
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
  const watchRow = document.getElementById('recordings-watch-row');
  const kicker = document.getElementById('recordings-inbox-kicker');
  const showMoreBtn = document.getElementById('recordings-show-more');
  if (!section) return;

  const recordings = (state.recordings || []).filter((r) => r.has_recording);
  const watching = Boolean(state.watchingForRecording);
  const idle = state.status === 'idle';
  const scopeKey = recordingsScopeKey(state.context);
  if (scopeKey !== lastRecordingsScopeKey) {
    lastRecordingsScopeKey = scopeKey;
    recordingsVisibleCount = RECORDINGS_PAGE_SIZE;
  }

  section.style.display = idle && (watching || recordings.length > 0 || state.recordingsLoading) ? 'block' : 'none';
  if (watchRow) watchRow.style.display = watching ? 'flex' : 'none';
  if (kicker) {
    kicker.style.display = idle && shouldShowInboxKicker(state.context, {
      hasRecordings: recordings.length > 0,
      loading: Boolean(state.recordingsLoading),
    }) ? 'block' : 'none';
  }
  if (!idle) {
    if (showMoreBtn) showMoreBtn.style.display = 'none';
    pruneCallMemosFromList(state);
    return;
  }

  if (statusEl) {
    statusEl.textContent = WATCH_STATUS_COPY[state.watchPhase] || WATCH_STATUS_COPY.awaiting_recording;
  }
  if (dotEl) {
    dotEl.style.display = watching ? 'inline-block' : 'none';
  }
  const stopBtn = document.getElementById('recordings-stop-watch');
  if (stopBtn) stopBtn.style.display = watching ? '' : 'none';

  if (!listEl) {
    if (showMoreBtn) showMoreBtn.style.display = 'none';
    pruneCallMemosFromList(state);
    return;
  }

  if (!recordings.length) {
    listEl.innerHTML = state.recordingsLoading
      ? '<div class="live-loader live-loader--inline" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></div>'
      : '';
    if (showMoreBtn) showMoreBtn.style.display = 'none';
    pruneCallMemosFromList(state);
    return;
  }

  const visible = recordings.slice(0, recordingsVisibleCount);
  listEl.innerHTML = '';
  visible.forEach((rec) => {
    const row = document.createElement('div');
    row.className = 'recording-row';
    const action = getRecordingAction(rec);
    const pill = getMemoStatusPill(rec);
    const dateStr = formatCallTimestamp(rec.timestamp || rec.timestamp_ms);
    const durStr = formatCallDuration(callDurationSeconds(rec));
    const meta = [dateStr !== 'Unknown date' ? dateStr : null, durStr].filter(Boolean).join(' · ');
    const title = rec.title || 'Call';

    row.innerHTML = `
      <div class="recording-row-main">
        <span class="activity-kind">Call</span>
        <span class="recording-row-title">${escapeHtml(title)}</span>
        ${meta ? `<span class="recording-row-meta">${escapeHtml(meta)}</span>` : ''}
      </div>
      <div class="recording-row-actions">
        ${pill?.busy ? busyStatusHtml(pill.text) : ''}
        ${action
          ? `<button type="button" class="btn-recording-action" data-call-id="${escapeHtml(rec.call_id)}" data-action="${action.action}"${action.memoId ? ` data-memo-id="${escapeHtml(action.memoId)}"` : ''}>${escapeHtml(action.label)}</button>`
          : ''}
      </div>
    `;
    listEl.appendChild(row);
  });

  listEl.querySelectorAll('.btn-recording-action').forEach((btn) => {
    btn.addEventListener('click', handleRecordingAction);
  });
  if (showMoreBtn) {
    showMoreBtn.style.display = recordings.length > recordingsVisibleCount ? '' : 'none';
  }
  pruneCallMemosFromList(state);
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
      chrome.runtime.sendMessage({
        type: 'SET_STATE',
        state: { status: 'processing', processingSource: 'hubspot_call' },
      }).catch(() => {});
      setProcessingScreenMode('hubspot_call');
      showScreen('processing');
      const res = await chrome.runtime.sendMessage({ type: 'PROCESS_HUBSPOT_CALL', callId });
      if (res?.error) throw new Error(res.error);
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
    if (lastBgState) renderState({ ...lastBgState, status: 'idle' });
    else showScreen('record');
  }
}

/** Set processing screen text: 'transcribing' | 'extracting' | 'hubspot_call' */
function setProcessingScreenMode(mode) {
  const sub = document.getElementById('processing-subtitle');
  const title = document.getElementById('processing-title');
  const kind = mode === 'extracting' ? 'extracting' : 'transcribing';
  startProcessingElapsed(kind);

  if (kind === 'extracting') {
    if (sub) sub.textContent = 'Working';
    if (title) title.textContent = 'Updating fields';
  } else {
    if (sub) sub.textContent = 'Working';
    if (title) title.textContent = 'Getting the transcript';
  }
}

function renderListenButton(state) {
  const btn = document.getElementById('listen-tab-button');
  const label = document.getElementById('listen-tab-label');
  if (!btn) return;
  const model = listenUiModel({
    listenPhase: resolveListenPhase(state),
    isCopilotListening: state.isCopilotListening,
    copilotError: state.copilotError,
    tabTitle: state.copilotTabTitle,
    heardAnything: Boolean(state.finalTranscript || state.interimTranscript),
  });
  const active = model.phase === 'live' || model.phase === 'starting';
  btn.classList.toggle('listening', active);
  btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  if (label) label.textContent = model.buttonLabel;
  btn.style.display = state.isRecording ? 'none' : '';
  renderListenStatus(state, model);
}

function renderListenStatus(state, model = listenUiModel(state)) {
  const el = document.getElementById('listen-status');
  if (!el) return;
  if (state.isRecording || !model.line) {
    el.style.display = 'none';
    el.textContent = '';
    el.dataset.phase = 'idle';
    return;
  }
  el.style.display = 'block';
  el.textContent = model.line;
  el.dataset.phase = model.phase;
}

function renderCopilotCard(state) {
  const card = document.getElementById('copilot-card');
  const say = document.getElementById('copilot-say-this');
  const heard = document.getElementById('copilot-heard');
  const next = document.getElementById('copilot-next');
  const err = document.getElementById('copilot-error');
  if (!card) return;

  if (!state.isCopilotListening && state.listenPhase !== 'live') {
    card.style.display = 'none';
    return;
  }

  card.style.display = 'block';
  const suggestion = state.copilotSuggestion;
  if (err) {
    err.style.display = state.copilotError ? 'block' : 'none';
    err.textContent = state.copilotError || '';
  }
  if (state.copilotIsLoading && !suggestion) {
    if (say) say.textContent = 'Coaching in real time…';
  } else if (suggestion?.say_this) {
    if (say) say.textContent = suggestion.say_this;
  } else if (say) {
    say.textContent = 'Waiting for the other side to finish speaking…';
  }
  if (heard) {
    const turn = state.copilotLastTurn;
    heard.style.display = turn ? 'block' : 'none';
    heard.textContent = turn ? `They said: “${turn}”` : '';
  }
  if (next) {
    const q = suggestion?.next_question;
    next.style.display = q ? 'block' : 'none';
    next.textContent = q ? `Next: ${q}` : '';
  }
}

// ============================================
// RENDER STATE (Core Logic)
// ============================================
function renderState(state) {
  if (!shouldPaintMainUi({ authStatus, stateAuthenticated: state?.authenticated })) {
    if (authStatus === 'signed_out') {
      enterLoggedOut();
    }
    return;
  }
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
  const idleTools = document.querySelector('.idle-tools');
  const shortcutBox = document.getElementById('shortcut-box');

  if (pasteSection) pasteSection.style.display = 'none';
  if (mainActions) mainActions.style.display = 'flex';

  // Recording UI
  if (state.isRecording) {
    stopIdleContextPoll();
    showScreen('record');
    recordButton.classList.add('recording');
    document.getElementById('record-status-label').textContent = 'Recording';
    liveTranscriptContainer.style.display = 'block';
    if (idleTools) idleTools.style.display = 'none';
    if (shortcutBox) shortcutBox.style.display = 'none';
    setIdleListsHidden();
    if (pasteToggle) pasteToggle.style.display = 'none';
    if (pasteSection) pasteSection.style.display = 'none';
    renderListenButton(state);
    renderCopilotCard({ isCopilotListening: false });

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

  if (state.isCopilotListening || state.status === 'copilot' || state.listenPhase === 'starting') {
    stopIdleContextPoll();
    const model = listenUiModel({
      listenPhase: resolveListenPhase(state),
      isCopilotListening: state.isCopilotListening,
      copilotError: state.copilotError,
      tabTitle: state.copilotTabTitle,
      heardAnything: Boolean(state.finalTranscript || state.interimTranscript),
    });
    showScreen('record');
    recordButton.classList.remove('recording');
    recordButton.disabled = true;
    document.getElementById('record-status-label').textContent =
      model.phase === 'starting' ? 'Starting' : 'Listening';
    liveTranscriptContainer.style.display = 'block';
    const transcriptLabel = liveTranscriptContainer.querySelector('.transcript-label');
    if (transcriptLabel) {
      transcriptLabel.textContent = model.live ? 'Hearing this tab' : 'Starting listen';
    }
    if (idleTools) {
      idleTools.style.display = 'grid';
      idleTools.style.gridTemplateColumns = '1fr';
    }
    if (shortcutBox) shortcutBox.style.display = 'none';
    setIdleListsHidden();
    if (pasteToggle) pasteToggle.style.display = 'none';
    if (pasteSection) pasteSection.style.display = 'none';
    const dealContextBadge = document.getElementById('deal-context-badge');
    if (dealContextBadge) dealContextBadge.style.display = 'none';
    renderRecordContextStrip(state);
    renderListenButton(state);
    renderCopilotCard(state);

    liveTranscriptText.innerHTML = state.finalTranscript
      ? `${state.finalTranscript} <span style="opacity:0.5">${state.interimTranscript || ''}</span>`
      : `<span style="opacity:0.5">${model.line || 'Capturing this tab’s audio…'}</span>`;
    liveTranscriptContainer.scrollTop = liveTranscriptContainer.scrollHeight;
    return;
  }

  recordButton.disabled = false;
  recordButton.classList.remove('recording');
  document.getElementById('record-status-label').textContent = 'Record';
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
        if (pt) pt.textContent = 'Getting the transcript';
        if (pm) pm.textContent = 'Writing the call down…';
      }
      
      fillShortcutHint();
      if (idleTools) {
        idleTools.style.display = 'grid';
        idleTools.style.gridTemplateColumns = '';
      }
      if (shortcutBox) shortcutBox.style.display = '';
      if (pasteToggle) pasteToggle.style.display = '';
      if (mainActions) mainActions.style.display = 'flex';
      if (pasteSection) pasteSection.style.display = 'none';

      previewLoaded = false;
      currentMemoId = null;
      insightsMemoId = null;
      actionItemsInitialized = false;
      reviewActionItems = [];
      editedProposedUpdates = null;
      omittedProposedKeys = new Set();
      renderRecordContextStrip(state);
      syncPageRecordScope(state.context);
      renderRecordingsSection(state);
      renderListenButton(state);
      renderCopilotCard(state);
      const scope = getRecentMemosScope(state.context);
      const scopeChanged = scope.key !== recentMemosScopeKey;
      if (scopeChanged) {
        recentMemosScopeKey = scope.key;
        recentMemosLoaded = false;
        recentMemosFetchGen += 1;
        const memosList = document.getElementById('recent-memos-list');
        if (memosList) memosList.innerHTML = '';
      }
      if (scope.skip || !shouldFetchVocifyMemos(state.context)) {
        recentMemosLoaded = true;
        const memosList = document.getElementById('recent-memos-list');
        const memosSection = document.getElementById('recent-memos-section');
        if (memosList) memosList.innerHTML = '';
        if (memosSection) memosSection.style.display = 'none';
        syncActivityEmptyState(state);
      } else if (lastRenderedStatus !== 'idle' || !recentMemosLoaded || scopeChanged) {
        loadRecentMemos(scope);
      } else {
        pruneCallMemosFromList(state);
      }
      startIdleContextPoll();
      break;
      
    case 'processing':
      stopIdleContextPoll();
      setProcessingScreenMode(state.processingSource === 'hubspot_call' ? 'hubspot_call' : 'transcribing');
      showScreen('processing');
      break;
      
    case 'review':
      stopIdleContextPoll();
      showScreen('review');
      renderReviewRecordName(state.context);
      if (state.currentMemoId && !sameMemoId(currentMemoId, state.currentMemoId)) {
        currentMemoId = state.currentMemoId;
        previewLoaded = false;
        lastPreviewData = null;
        editedProposedUpdates = null;
        omittedProposedKeys = new Set();
        reviewActionItems = [];
        actionItemsInitialized = false;
        insightsMemoId = null;
        userSelectedDealId = null;
        userSelectedContactId = null;
        createNewDealRequested = false;
        applyReviewLayout('loading');
      }
      if (state.currentMemoId) {
        if (!isReviewBodyVisible()) applyReviewLayout('loading');
        handleReviewState(state.currentMemoId, state.context);
      } else {
        applyReviewLayout('error', 'Nothing to review yet.');
      }
      break;
      
    case 'success':
      stopIdleContextPoll();
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

function isReviewBodyVisible() {
  return ['pending-transcript-section', 'proposed-changes-main', 'review-loading-section'].some((id) => {
    const el = document.getElementById(id);
    return el && el.style.display && el.style.display !== 'none';
  });
}

function applyReviewLayout(mode, message = '') {
  const pendingSection = document.getElementById('pending-transcript-section');
  const proposedMain = document.getElementById('proposed-changes-main');
  const reviewActions = document.getElementById('review-actions');
  const stepLabel = document.getElementById('review-step-label');
  const reviewScreen = document.getElementById('screen-review');
  const loadingSection = document.getElementById('review-loading-section');
  const loadingText = document.getElementById('review-loading-text');
  const loadingBack = document.getElementById('review-loading-back');

  if (reviewScreen) {
    reviewScreen.classList.toggle('review-mode-transcript', mode === 'pending_transcript');
    reviewScreen.classList.toggle('review-mode-changes', mode === 'pending_review');
  }

  if (pendingSection) pendingSection.style.display = mode === 'pending_transcript' ? 'flex' : 'none';
  if (proposedMain) {
    proposedMain.style.display = mode === 'pending_review' ? 'flex' : 'none';
    proposedMain.style.flexDirection = mode === 'pending_review' ? 'column' : '';
  }
  if (reviewActions) reviewActions.style.display = mode === 'pending_review' ? 'flex' : 'none';

  const showLoading = mode === 'loading' || mode === 'error';
  if (loadingSection) loadingSection.style.display = showLoading ? 'flex' : 'none';
  if (loadingText) {
    loadingText.textContent = mode === 'error'
      ? (message || 'Could not load this review.')
      : (message || 'Opening review…');
  }
  if (loadingBack) loadingBack.style.display = mode === 'error' ? '' : 'none';

  if (stepLabel) {
    if (mode === 'pending_transcript') stepLabel.textContent = 'Review transcript';
    else if (mode === 'pending_review') stepLabel.textContent = 'Review & sync';
    else stepLabel.textContent = 'Review';
  }

  if (mode === 'pending_review') {
    const collapsible = document.getElementById('transcript-collapsible');
    if (collapsible) collapsible.open = true;
  }
}

/** Route review to pending-transcript or proposed-changes based on memo status */
async function enrichPageAssociations(context) {
  if (!context?.recordId) return context;
  if (context.objectType === 'company' && !Array.isArray(context.companyContacts)) {
    try {
      const fetched = await chrome.runtime.sendMessage({
        type: 'GET_COMPANY_CONTEXT',
        companyId: context.recordId,
      });
      if (fetched && !fetched.error) {
        return {
          ...context,
          companyName: fetched.companyName,
          companyId: context.recordId,
          contactId: fetched.contactId,
          companyContacts: fetched.contacts || [],
        };
      }
    } catch (_) { /* keep raw context */ }
  }
  if (context.objectType === 'deal' && !Array.isArray(context.dealContacts)) {
    try {
      const fetched = await chrome.runtime.sendMessage({
        type: 'GET_DEAL_CONTEXT',
        dealId: context.recordId,
      });
      if (fetched && !fetched.error) {
        return {
          ...context,
          dealName: fetched.raw_extraction?.dealname || context.dealName,
          companyName: fetched.companyName,
          companyId: fetched.companyId,
          contactId: fetched.contactId,
          contactName: fetched.contactName,
          contactEmail: fetched.contactEmail,
          dealContacts: fetched.contacts || [],
        };
      }
    } catch (_) { /* keep raw context */ }
  }
  return context;
}

async function handleReviewState(memoId, context) {
  startSessionHeartbeat();
  const gen = ++reviewFetchGen;
  if (!isReviewBodyVisible()) applyReviewLayout('loading');
  try {
    const memo = await api.getMemo(memoId);
    if (gen !== reviewFetchGen) return;
    if (!isCurrentReviewMemo(memoId)) return;
    await applyReviewPresentation(
      resolveReviewPresentation({ memo, isAuthFailure }),
      { memoId, context, memo, gen },
    );
  } catch (e) {
    if (gen !== reviewFetchGen) return;
    console.error('[Popup] handleReviewState error:', e);
    await applyReviewPresentation(
      resolveReviewPresentation({ error: e, isAuthFailure }),
      { memoId, context, gen },
    );
  }
}

async function applyReviewPresentation(presentation, { memoId, context, memo = null, gen }) {
  if (authStatus !== 'signed_in') return;
  if (presentation.mode === 'login') {
    enterLoggedOut();
    return;
  }
  if (presentation.mode === 'processing') {
    chrome.runtime.sendMessage({
      type: 'SET_STATE',
      state: {
        status: 'processing',
        currentMemoId: String(memoId),
        processingSource: lastBgState?.processingSource || 'hubspot_call',
      },
    }).catch(() => {});
    return;
  }
  if (presentation.mode === 'error') {
    applyReviewLayout('error', presentation.message);
    return;
  }
  if (presentation.mode === 'pending_transcript') {
    applyReviewLayout('pending_transcript');
    renderReviewRecordName(context);
    syncTranscriptModalDeal(context);
    if (presentation.failed) {
      showExtractionError(presentation.message);
    }
    loadTranscriptForReview(memoId);
    return;
  }

  applyReviewLayout('pending_review');
  renderReviewRecordName(context);
  syncPageRecordScope(context);
  context = await enrichPageAssociations(context);
  if (gen !== reviewFetchGen) return;
  if (!isCurrentReviewMemo(memoId)) return;
  if (context) lastBgState = { ...(lastBgState || {}), context };
  const onCompanyPage = context?.objectType === 'company' && context?.recordId;
  const targets = currentReviewTargets(context);
  if (!previewLoaded || !sameMemoId(currentMemoId, memoId)) {
    currentMemoId = memoId;
    previewLoaded = true;
    if (needsAssociatedContactPick(context, targets.contactId)) {
      currentDealId = targets.dealId;
      currentCompanyId = targets.companyId;
      lastPreviewData = { ...(lastPreviewData || {}), selected_contact: null };
      if (context.objectType === 'deal') {
        const dealNameEl = document.getElementById('target-deal-name');
        const dealReasonEl = document.getElementById('target-deal-reason');
        if (dealNameEl) dealNameEl.textContent = context.dealName || 'Deal on this page';
        if (dealReasonEl) dealReasonEl.textContent = 'This HubSpot deal';
      }
      renderContactTarget({ selected_contact: null, contact_candidates: [] });
      renderReviewRecordName(context, lastPreviewData);
      updateApproveButtonState(lastPreviewData);
    } else {
      let extractionOverride = null;
      if (onCompanyPage && !targets.contactId && context.companyName) {
        try {
          const memoFull = await api.getMemo(memoId);
          const base = memoFull?.extraction && typeof memoFull.extraction === 'object'
            ? { ...memoFull.extraction }
            : {};
          base.companyName = context.companyName;
          extractionOverride = base;
        } catch (_) { /* optional */ }
      }
      await loadPreview(memoId, targets.dealId, extractionOverride, targets.contactId);
    }
  }
  if (gen !== reviewFetchGen) return;
  showUsePageRecordOption(context);
  const preview = lastPreviewData;
  const tx = preview?.transcript || memo?.transcript || '';
  renderTranscriptConversation(tx, {
    container: document.getElementById('review-transcript-conversation'),
    labels: reviewSpeakerLabels(context),
  });
  const noteCb = document.getElementById('create-note-checkbox');
  const noteRow = document.getElementById('create-note-row');
  if (noteCb) {
    noteCb.checked = !!tx.trim();
    noteCb.disabled = !tx.trim();
  }
  if (noteRow) noteRow.classList.toggle('is-disabled', !tx.trim());
  syncNoteToggleCopy(preview);
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

function reviewSpeakerLabels(context = lastBgState?.context, preview = lastPreviewData) {
  const them = firstName(
    preview?.selected_contact?.name ||
    context?.contactName ||
    ''
  );
  return { s1: 'You', s2: them || 'Them' };
}

function renderTranscriptConversation(text, { container = null, labels = null } = {}) {
  const convo = container || document.getElementById('transcript-conversation');
  const hidden = document.getElementById('transcript-content');
  const normalized = normalizeDiarizedTranscript(text);
  if (hidden && !container) hidden.value = normalized;

  if (!convo) return;

  const turns = parseTranscriptTurns(normalized);
  const roleLabels = labels || reviewSpeakerLabels(lastBgState?.context);

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
      label.textContent = speakerDisplayLabel(row.dataset.speaker || turn.speaker, roleLabels);
      row.appendChild(label);
    }

    const bubble = document.createElement('div');
    bubble.className = 'transcript-bubble';
    bubble.textContent = turn.text;
    row.appendChild(bubble);
    convo.appendChild(row);
  });
}

function syncNoteToggleCopy(preview) {
  const desc = document.querySelector('.note-toggle-desc');
  if (!desc) return;
  const skipDeal = !!preview?.skip_deal && !preview?.selected_deal;
  desc.textContent = skipDeal
    ? 'Posts this note + transcript on the contact timeline'
    : 'Posts this note + transcript on the deal timeline';
}

/** Show "Use X on this page" for deal / contact / company HubSpot pages */
function showUsePageRecordOption(context) {
  const opt = document.getElementById('use-page-record-option');
  const btn = document.getElementById('btn-use-page-record');
  if (!opt || !btn) return;
  const type = context?.objectType;
  const ok = !!context?.recordId && ['deal', 'contact', 'company'].includes(type);
  if (!ok) {
    opt.style.display = 'none';
    return;
  }
  const targets = currentReviewTargets(context);
  const alreadyOnPage =
    (type === 'deal' && targets.dealId === context.recordId) ||
    (type === 'contact' && targets.contactId === context.recordId) ||
    (type === 'company' && targets.companyId === context.recordId);
  opt.style.display = alreadyOnPage ? 'none' : 'block';
  const labels = {
    deal: 'Back to this HubSpot deal',
    contact: 'Back to this HubSpot contact',
    company: 'Back to this HubSpot company',
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
    if (!isCurrentReviewMemo(memoId)) return;
    renderTranscriptConversation(memo?.transcript || '', {
      labels: reviewSpeakerLabels(lastBgState?.context),
    });
    const timing = document.getElementById('transcript-timing');
    const ready = memoReadyInLabel(memo);
    if (timing) {
      timing.textContent = ready;
      timing.style.display = ready ? '' : 'none';
    }
    if (hidden) hidden.readOnly = true;
    if (memo?.status === 'failed') {
      showExtractionError(memo?.errorMessage || 'Extraction failed. Click Retry to try again.');
    } else if (memo?.status === 'extracting') {
      showExtractionError('Extraction is still in progress or stuck. Click Retry to try again.');
    } else {
      hideExtractionError();
    }
  } catch (e) {
    console.error('[Popup] Failed to load transcript:', e);
    if (isAuthFailure(e)) {
      enterLoggedOut();
      return;
    }
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
  if (!listElement) return;

  const resolved = scope || getRecentMemosScope(null);
  const gen = ++recentMemosFetchGen;
  const section = document.getElementById('recent-memos-section');

  if (resolved.skip || !shouldFetchVocifyMemos(lastBgState?.context)) {
    recentMemosLoaded = true;
    listElement.innerHTML = '';
    if (section) section.style.display = 'none';
    syncActivityEmptyState(lastBgState);
    return;
  }

  try {
    const memos = await chrome.runtime.sendMessage({
      type: 'GET_RECENT_MEMOS',
      dealId: resolved.dealId || undefined,
      contactId: resolved.contactId || undefined,
    });
    if (gen !== recentMemosFetchGen) return;
    if (resolved.key !== recentMemosScopeKey) return;

    if (memos && !memos.error && Array.isArray(memos)) {
      recentMemosLoaded = true;
      const vocifyMemos = memos.filter((memo) => isVocifyMemo(memo, hubspotCallMemoIds(lastBgState)));
      if (vocifyMemos.length === 0) {
        listElement.innerHTML = '';
        if (section) section.style.display = 'none';
        syncActivityEmptyState(lastBgState);
        return;
      }

      if (section) section.style.display = 'block';
      listElement.innerHTML = '';
      vocifyMemos.forEach((memo) => {
        const item = document.createElement('div');
        item.className = 'memo-item';
        item.dataset.memoId = String(memo.id);

        const date = new Date(memo.createdAt || memo.created_at).toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });

        const busy = memoBusyLabel(memo.status);
        const canContinue = ['pending_review', 'pending_transcript'].includes(memo.status);
        let statusClass = 'status-processing';
        let statusText = (memo.status || '').replace(/_/g, ' ');
        if (memo.status === 'pending_review' || memo.status === 'pending_transcript') {
          statusClass = 'status-pending';
          statusText = 'Review';
        }
        if (memo.status === 'approved') {
          statusClass = 'status-approved';
          statusText = 'Synced';
        }
        if (memo.status === 'failed') statusClass = 'status-failed';

        const snippet = memo.transcript
          ? memo.transcript.replace(/\s+/g, ' ').trim().slice(0, 48)
          : '';

        item.innerHTML = `
          <div class="memo-info">
            <span class="activity-kind">Memo</span>
            <span class="memo-status">${snippet ? `${escapeHtml(snippet)}${snippet.length >= 48 ? '…' : ''}` : 'No transcript yet'}</span>
            <span class="memo-date">${escapeHtml(date)}</span>
          </div>
          ${busy ? busyStatusHtml(busy) : ''}
          ${canContinue ? '<button type="button" class="btn-recording-action">Continue</button>' : ''}
          ${!busy && !canContinue ? `<span class="status-pill ${statusClass}">${statusText}</span>` : ''}
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
      syncActivityEmptyState(lastBgState);
    }
  } catch (e) {
    if (gen !== recentMemosFetchGen) return;
    console.error('[Popup] Failed to load recent memos:', e);
    if (section) section.style.display = 'none';
    syncActivityEmptyState(lastBgState);
  }
}

function visibleProposedUpdates(updates) {
  if (editedProposedUpdates !== null) {
    return editedProposedUpdates.filter(Boolean);
  }
  return (updates || []).filter((u) => {
    const key = proposedFieldKey(u);
    return !key || !omittedProposedKeys.has(key);
  });
}

async function loadPreview(memoId, dealId = null, extraction = null, contactId = null, opts = null) {
  const resetEdits = !!opts?.resetEdits;
  if (resetEdits || !lastPreviewData) {
    document.getElementById('target-deal-name').textContent = 'Loading...';
    document.getElementById('target-deal-reason').textContent = '';
    proposedUpdatesList.innerHTML = '<div class="spinner" style="margin: 20px auto;"></div>';
  }

  const createNewDeal = !!(opts && opts.createNewDeal) || createNewDealRequested;
  if (createNewDeal) createNewDealRequested = true;

  const requestedDealId = createNewDeal ? null : (dealId || null);
  const requestedContactId = contactId || null;

  try {
    const preview = await chrome.runtime.sendMessage({
      type: 'GET_PREVIEW',
      memoId,
      dealId: requestedDealId,
      contactId: requestedContactId || undefined,
      createNewDeal: createNewDeal || undefined,
      extraction: extraction || undefined
    });

    if (!isCurrentReviewMemo(memoId)) return;
    if (preview && !preview.error) {
      const bound = bindPreviewIds({
        requestedDealId,
        requestedContactId,
        preview,
        adoptPreviewContact:
          !!requestedContactId || !['deal', 'company'].includes(lastBgState?.context?.objectType),
      });
      if (requestedDealId) {
        lastPreviewData = { ...preview };
      } else if (createNewDeal) {
        lastPreviewData = { ...preview, selected_deal: null, is_new_deal: true, skip_deal: false };
      } else if (requestedContactId || preview.selected_contact) {
        lastPreviewData = { ...preview, selected_deal: null, skip_deal: true, is_new_deal: false };
      } else {
        lastPreviewData = { ...preview };
      }
      if (!requestedContactId && ['deal', 'company'].includes(lastBgState?.context?.objectType)) {
        lastPreviewData = { ...lastPreviewData, selected_contact: null };
      }
      previewLoaded = true;
      currentDealId = bound.dealId;
      currentContactId = bound.contactId;
      currentCompanyId =
        bound.companyId ||
        lastBgState?.context?.companyId ||
        (lastBgState?.context?.objectType === 'company' ? lastBgState.context.recordId : null) ||
        null;

      renderContactTarget(lastPreviewData);

      const match = lastPreviewData.selected_deal;
      const skipDeal = !!lastPreviewData.skip_deal && !match;
      const pageDeal =
        lastBgState?.context?.objectType === 'deal' &&
        lastBgState.context.recordId &&
        match?.deal_id === lastBgState.context.recordId;
      document.getElementById('target-deal-name').textContent = match
        ? match.deal_name
        : skipDeal
          ? 'Contact only — no deal'
          : (createNewDeal || lastPreviewData.is_new_deal ? 'New Deal' : 'No deal selected');
      const reasonText = match
        ? (pageDeal ? 'This HubSpot deal' : (match.match_reason === 'Manual Selection' ? 'From current page' : `Matched via ${(match.match_reason || 'AI').toLowerCase()}`))
        : skipDeal
          ? 'Only the contact on this page will be updated'
          : (createNewDeal || lastPreviewData.is_new_deal
            ? 'A new record will be created'
            : 'Choose a deal or create a new one');
      document.getElementById('target-deal-reason').textContent = reasonText;

      const dealLabel = document.getElementById('deal-target-label');
      const changeBtn = document.getElementById('btn-change-deal');
      if (dealLabel) {
        dealLabel.textContent = lastPreviewData.selected_contact ? 'Deal (optional)' : 'Deal';
      }
      if (changeBtn) {
        changeBtn.textContent = lastPreviewData.selected_contact ? 'Choose deal' : 'Change deal';
      }

      if (opts?.resetEdits) {
        editedProposedUpdates = null;
        omittedProposedKeys = new Set();
        actionItemsInitialized = false;
        reviewActionItems = [];
      }
      initCallInsights(lastPreviewData);
      try {
        const memo = await api.getMemo(memoId);
        const summaryEl = document.getElementById('review-summary');
        if (summaryEl && !summaryEl.value.trim() && memo?.extraction?.summary) {
          summaryEl.value = memo.extraction.summary;
        }
        if (!actionItemsInitialized && Array.isArray(memo?.extraction?.nextSteps)) {
          reviewActionItems = memo.extraction.nextSteps
            .filter((s) => s && String(s).trim())
            .map((text) => ({ id: ++actionItemIdSeq, text: String(text).trim(), checked: true }));
          actionItemsInitialized = true;
          renderActionItems();
        }
      } catch (_) { /* optional enrichment */ }

      const decision = evaluateDealDecision(lastPreviewData, { createNewDeal });
      const pageHasRecord = !!lastBgState?.context?.recordId &&
        ['deal', 'contact', 'company'].includes(lastBgState.context.objectType);
      if (decision.autoSelectDealId && !createNewDeal && !pageHasRecord) {
        userSelectedDealId = decision.autoSelectDealId;
        createNewDealRequested = false;
        await loadPreview(memoId, decision.autoSelectDealId, null, requestedContactId);
        return;
      }
      renderDealDecisionUI(lastPreviewData);
      updateApproveButtonState(lastPreviewData);
      renderProposedUpdates(visibleProposedUpdates(lastPreviewData.proposed_updates || []), lastPreviewData.available_fields || []);
      renderReviewRecordName(lastBgState?.context, lastPreviewData);
      showUsePageRecordOption(lastBgState?.context);
      syncNoteToggleCopy(lastPreviewData);
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
  const targets = currentReviewTargets();
  const candidates = Array.isArray(preview?.contact_candidates) ? preview.contact_candidates : [];
  const needsContactPick =
    needsAssociatedContactPick(lastBgState?.context, targets.contactId) ||
    (!preview?.selected_contact && candidates.length > 0);
  if (needsContactPick) {
    approveSyncButton.disabled = true;
    approveSyncButton.textContent = 'Pick a contact first';
    return;
  }
  if (needsDealDecision && !dealDecisionMade) {
    approveSyncButton.disabled = true;
    approveSyncButton.textContent = 'Pick a deal first';
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
  const contactName = preview?.selected_contact?.name || preview?.selected_contact?.email;
  const dealName = preview?.selected_deal?.deal_name;
  if (skipDeal && contactName) {
    approveSyncButton.textContent = `Update ${contactName}`;
  } else if (dealName && contactName) {
    approveSyncButton.textContent = `Update ${dealName}`;
  } else if (dealName) {
    approveSyncButton.textContent = `Update ${dealName}`;
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
  const selectedDealId = preview?.selected_deal?.deal_id || null;
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
  if (card) card.style.display = showWeakConfirm ? 'none' : 'block';

  if (hint) {
    hint.textContent = showWeakConfirm
      ? "We couldn't match this to a deal. Pick one, or create a new deal."
      : 'Linked deals on this contact';
  }

  list.innerHTML = '';
  matches.slice(0, 5).forEach((m) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'matched-deal-item';
    if (selectedDealId && m.deal_id === selectedDealId) btn.classList.add('is-selected');
    btn.innerHTML = `<strong class="deal-title">${escapeHtml(m.deal_name || 'Deal')}</strong><br><span class="deal-subtitle">${escapeHtml(m.match_reason || '')}</span>`;
    btn.addEventListener('click', () => selectDealTarget(m.deal_id));
    list.appendChild(btn);
  });
}

function selectDealTarget(dealId) {
  createNewDealRequested = false;
  needsDealDecision = false;
  dealDecisionMade = true;
  previewLoaded = false;
  userSelectedDealId = dealId;
  currentDealId = dealId;
  const targets = currentReviewTargets(lastBgState?.context, { userDealId: dealId });
  loadPreview(currentMemoId, targets.dealId, null, targets.contactId, { resetEdits: true });
}

function createNewDealTarget() {
  createNewDealRequested = true;
  needsDealDecision = false;
  dealDecisionMade = true;
  previewLoaded = false;
  userSelectedDealId = null;
  currentDealId = null;
  const searchBox = document.getElementById('deal-search-box');
  if (searchBox) searchBox.style.display = 'none';
  const targets = currentReviewTargets(lastBgState?.context, { userDealId: null, createNewDeal: true });
  loadPreview(currentMemoId, null, null, targets.contactId, { createNewDeal: true, resetEdits: true });
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
  const associated = associatedContactsFromContext(lastBgState?.context);
  const associatedPickList =
    !selected && !candidates.length && associated.length > 1 ? associated : [];

  if (!selected && !candidates.length && !associatedPickList.length) {
    section.style.display = 'none';
    return;
  }
  section.style.display = 'block';

  if (selected) {
    if (card) card.style.display = 'block';
    if (nameEl) nameEl.textContent = selected.name || selected.email || 'Contact';
    const onThisContact =
      lastBgState?.context?.objectType === 'contact' &&
      lastBgState.context.recordId === selected.contact_id;
    const bits = [
      onThisContact ? 'This HubSpot contact' : selected.match_reason,
      selected.email,
      selected.phone,
      selected.company_name,
    ].filter(Boolean);
    if (metaEl) metaEl.textContent = bits.join(' · ');
    if (candidatesEl) {
      candidatesEl.style.display = 'none';
      candidatesEl.innerHTML = '';
    }
    return;
  }

  if (card) card.style.display = 'none';
  const pick = candidates.length ? candidates : associatedPickList;
  const pageType = lastBgState?.context?.objectType;
  if (candidatesEl) {
    candidatesEl.style.display = 'block';
    candidatesEl.innerHTML = '';
    const hint = document.createElement('p');
    hint.className = 'deal-subtitle';
    hint.style.margin = '0 0 8px';
    hint.textContent = candidates.length
      ? 'Several contacts matched this call. Pick who to update:'
      : pageType === 'deal'
        ? 'This deal has several contacts. Pick who to update:'
        : 'This company has several contacts. Pick who to update:';
    candidatesEl.appendChild(hint);
    pick.forEach((c) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'matched-deal-item';
      btn.innerHTML = `<strong>${escapeHtml(c.name || 'Contact')}</strong><br><span class="deal-subtitle">${escapeHtml([c.email, c.phone, c.company_name].filter(Boolean).join(' · '))}</span>`;
      btn.addEventListener('click', () => {
        userSelectedContactId = c.contact_id;
        currentContactId = c.contact_id;
        const targets = currentReviewTargets(lastBgState?.context, { userContactId: c.contact_id });
        loadPreview(currentMemoId, targets.dealId, null, targets.contactId, { resetEdits: true });
      });
      candidatesEl.appendChild(btn);
    });
  }
}

function initCallInsights(preview) {
  const updates = preview?.proposed_updates || [];
  const summaryEl = document.getElementById('review-summary');
  const memoChanged = insightsMemoId !== currentMemoId;
  insightsMemoId = currentMemoId;
  if (memoChanged && summaryEl) summaryEl.value = '';
  if (actionItemsInitialized && !memoChanged) {
    renderActionItems();
    return;
  }

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
  actionItemsInitialized = true;
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
      actionItemsInitialized = true;
      reviewActionItems = reviewActionItems.filter((x) => x.id !== item.id);
      renderActionItems();
    });
    list.appendChild(row);
  });
}

function addActionItem(text = '') {
  actionItemsInitialized = true;
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
      const canEdit = canEditOrRemoveProposedField(update);
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
            ${canEdit ? `
              <div class="update-actions">
                <button class="update-action-btn edit" title="Edit">${editIcon}</button>
                <button class="update-action-btn remove" title="Skip this field this time">${removeIcon}</button>
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
        const removed = editedProposedUpdates[i];
        const key = proposedFieldKey(removed || update);
        if (key) omittedProposedKeys.add(key);
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
    (f) =>
      f?.name &&
      !isInsightsField(f.name) &&
      !sourceForAdd.some(
        (u) =>
          u &&
          u.field_name === f.name &&
          (u.object_type || 'deals') === (f.object_type || 'deals')
      )
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
              `<div class="add-field-opt" data-name="${escapeHtml(f.name)}" data-label="${escapeHtml(f.label)}" data-type="${escapeHtml(f.type)}" data-object-type="${escapeHtml(f.object_type || 'deals')}">${escapeHtml(({ deals: 'Deal', contacts: 'Contact', companies: 'Company' })[f.object_type || 'deals'] || 'Deal')} · ${escapeHtml(f.label)}</div>`
          )
          .join('');
        dropdown.querySelectorAll('.add-field-opt').forEach((opt) => {
          opt.onclick = () => {
            const objectType = opt.dataset.objectType || 'deals';
            const newUpdate = {
              field_name: opt.dataset.name,
              field_label: opt.dataset.label,
              field_type: opt.dataset.type || 'string',
              object_type: objectType,
              current_value: null,
              new_value: '',
              options: availableFields.find(
                (af) => af.name === opt.dataset.name && (af.object_type || 'deals') === objectType
              )?.options
            };
            const restoredKey = proposedFieldKey(newUpdate);
            if (restoredKey) omittedProposedKeys.delete(restoredKey);
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
  const updates = editedProposedUpdates !== null
    ? editedProposedUpdates.filter(Boolean)
    : (preview.proposed_updates || []);
  const summaryEl = document.getElementById('review-summary');
  const selectedSteps = reviewActionItems
    .filter((i) => i.checked && (i.text || '').trim())
    .map((i) => i.text.trim());

  return buildApproveExtraction({
    memoExtraction: memo?.extraction && typeof memo.extraction === 'object' ? memo.extraction : {},
    updates,
    omittedKeys: [...omittedProposedKeys],
    summary: summaryEl?.value || '',
    nextSteps: selectedSteps,
  });
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
          userSelectedDealId = deal.deal_id;
          selectDealTarget(deal.deal_id);
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

  if (!msg || !btn) return;
  const contactName =
    lastPreviewData?.selected_contact?.name || lastPreviewData?.selected_contact?.email;
  const dealName = result?.deal_name;
  const ctx = lastBgState?.context;

  if (dealName && contactName) {
    msg.textContent = `Updated ${dealName} and ${contactName} in HubSpot.`;
  } else if (dealName) {
    msg.textContent = `Updated ${dealName} in HubSpot.`;
  } else if (contactName) {
    msg.textContent = `Updated ${contactName} in HubSpot.`;
  } else {
    msg.textContent = 'CRM updated successfully.';
  }

  if (result?.deal_url) {
    btn.href = result.deal_url;
    btn.style.display = 'block';
  } else if (ctx?.hubId && result?.contact_id) {
    btn.href = buildHubSpotUrl({
      region: ctx.region,
      hubId: ctx.hubId,
      objectTypeId: '0-1',
      recordId: result.contact_id,
    });
    btn.style.display = 'block';
  } else if (ctx?.hubId && ctx.objectType === 'contact' && ctx.recordId) {
    btn.href = buildHubSpotUrl({
      region: ctx.region,
      hubId: ctx.hubId,
      objectTypeId: ctx.objectTypeId || '0-1',
      recordId: ctx.recordId,
    });
    btn.style.display = 'block';
  } else {
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
  const mainActions = document.querySelector('.main-actions');
  const shortcutBox = document.getElementById('shortcut-box');

  if (section) {
    section.style.display = 'block';
    if (mainActions) mainActions.style.display = 'none';
    if (shortcutBox) shortcutBox.style.display = 'none';
    setIdleListsHidden();
    document.getElementById('paste-transcript-input')?.focus();
  }
});

// Paste transcript cancel
document.getElementById('paste-transcript-cancel-btn')?.addEventListener('click', () => {
  const section = document.getElementById('paste-transcript-section');
  const input = document.getElementById('paste-transcript-input');

  if (section) section.style.display = 'none';
  if (input) input.value = '';
  if (lastBgState) {
    renderState(lastBgState);
  } else {
    const mainActions = document.querySelector('.main-actions');
    if (mainActions) mainActions.style.display = 'flex';
  }
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
    btn.textContent = 'Import';
    const section = document.getElementById('paste-transcript-section');
    const toggle = document.getElementById('paste-transcript-toggle');
    if (section) section.style.display = 'block';
    if (toggle) toggle.style.display = 'none';
  }
});

// Record button
recordButton.addEventListener('click', async () => {
  const state = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
  if (state.isCopilotListening) return;
  
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

document.getElementById('listen-tab-button')?.addEventListener('click', () => {
  // Chrome drops the click gesture if GET_STATE or tabs.query run first.
  // getMediaStreamId must be the first await on Listen.
  const phase = resolveListenPhase(lastBgState || {});
  if (phase === 'starting' || phase === 'live' || lastBgState?.isCopilotListening) {
    listenStartSeq += 1;
    lastBgState = {
      ...(lastBgState || {}),
      listenPhase: 'idle',
      status: 'idle',
      isCopilotListening: false,
      copilotError: null,
    };
    renderState(lastBgState);
    chrome.runtime.sendMessage(listenClickRuntimeMessage({
      isCopilotListening: true,
      listenPhase: 'live',
      commandSeq: listenStartSeq,
    }))
      .then(() => chrome.runtime.sendMessage({ type: 'GET_STATE' }))
      .then((next) => { if (next) renderState(next); })
      .catch((err) => console.error('[Popup] stop listen failed:', err));
    return;
  }

  const seq = ++listenStartSeq;
  lastBgState = {
    ...(lastBgState || {}),
    listenPhase: 'starting',
    status: 'copilot',
    copilotError: null,
  };
  renderState(lastBgState);

  const captureTabId = lastBgState?.captureTabId ?? null;
  requestTabCaptureStreamId(chrome.tabCapture, captureTabId)
    .then((streamId) => {
      if (seq !== listenStartSeq) return { cancelled: true };
      return chrome.runtime.sendMessage(listenClickRuntimeMessage({
        isCopilotListening: false,
        listenPhase: 'idle',
        captureTabId,
        streamId,
        commandSeq: seq,
      }));
    })
    .then((res) => {
      if (seq !== listenStartSeq || res?.cancelled) return null;
      if (res?.error) {
        lastBgState = {
          ...(lastBgState || {}),
          listenPhase: 'error',
          status: 'idle',
          isCopilotListening: false,
          copilotError: res.error,
        };
        renderState(lastBgState);
      }
      return chrome.runtime.sendMessage({ type: 'GET_STATE' });
    })
    .then((next) => { if (next) renderState(next); })
    .catch((err) => {
      if (seq !== listenStartSeq) return;
      lastBgState = {
        ...(lastBgState || {}),
        listenPhase: 'error',
        status: 'idle',
        isCopilotListening: false,
        copilotError: err?.message || 'Could not start tab audio. Click Listen again.',
      };
      renderState(lastBgState);
    });
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
  const targets = currentReviewTargets(lastBgState?.context);
  if (needsAssociatedContactPick(lastBgState?.context, targets.contactId)) return;
  const candidates = Array.isArray(lastPreviewData?.contact_candidates) ? lastPreviewData.contact_candidates : [];
  if (!lastPreviewData?.selected_contact && candidates.length > 0) return;
  if (selectedCallOutcome === 'lost' && !getEffectiveLostReason()) return;

  approveSyncButton.disabled = true;
  approveSyncButton.textContent = 'Syncing...';
  hideExtractionError();

  try {
    const extraction = await buildExtractionForApprove();
    const createNote = document.getElementById('create-note-checkbox')?.checked !== false;
    const skipDeal = !!targets.skipDeal;
    const response = await chrome.runtime.sendMessage({
      type: 'APPROVE_SYNC',
      memoId: currentMemoId,
      dealId: targets.dealId,
      isNewDeal: !!createNewDealRequested || (!targets.dealId && !skipDeal && !targets.contactId),
      extraction: extraction || undefined,
      createNote,
      contactId: targets.contactId || undefined,
      companyId: targets.companyId || undefined,
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
  chrome.runtime.sendMessage({
    type: 'SET_STATE',
    state: { status: 'idle' },
  });
});
document.getElementById('review-loading-back')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({
    type: 'SET_STATE',
    state: { status: 'idle' },
  });
});

document.getElementById('recordings-stop-watch')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'STOP_CALL_WATCH' });
  chrome.runtime.sendMessage({ type: 'GET_STATE' }).then((s) => renderState(s));
});
document.getElementById('recordings-show-more')?.addEventListener('click', () => {
  const total = (lastBgState?.recordings || []).filter((r) => r.has_recording).length;
  recordingsVisibleCount = nextVisibleCount(recordingsVisibleCount, total);
  if (lastBgState) renderRecordingsSection(lastBgState);
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

  lastPageRecordKey = null;
  syncPageRecordScope(ctx);
  lastBgState = { ...(lastBgState || state), context: ctx };
  createNewDealRequested = false;
  previewLoaded = false;

  if (ctx.objectType === 'company') {
    let companyCtx = ctx;
    if (!ctx.companyName || !Array.isArray(ctx.companyContacts)) {
      const fetched = await chrome.runtime.sendMessage({
        type: 'GET_COMPANY_CONTEXT',
        companyId: ctx.recordId,
      });
      if (fetched && !fetched.error) {
        companyCtx = {
          ...ctx,
          companyName: fetched.companyName,
          companyId: ctx.recordId,
          contactId: fetched.contactId,
          companyContacts: fetched.contacts || [],
        };
        lastBgState = { ...(lastBgState || state), context: companyCtx };
      }
    }
    const targets = currentReviewTargets(companyCtx);
    const contacts = Array.isArray(companyCtx.companyContacts) ? companyCtx.companyContacts : [];
    if (!targets.contactId && contacts.length > 1) {
      lastPreviewData = {
        ...(lastPreviewData || {}),
        selected_contact: null,
        contact_candidates: [],
        matched_deals: lastPreviewData?.matched_deals || [],
        skip_deal: true,
      };
      renderContactTarget({ selected_contact: null, contact_candidates: [] });
      approveSyncButton.disabled = true;
      approveSyncButton.textContent = 'Confirm Contact First';
      return;
    }
    let extractionOverride = null;
    if (!targets.contactId && (companyCtx.companyName || ctx.companyName)) {
      try {
        const memo = await api.getMemo(currentMemoId);
        const base = memo?.extraction && typeof memo.extraction === 'object' ? { ...memo.extraction } : {};
        base.companyName = companyCtx.companyName || ctx.companyName || base.companyName;
        extractionOverride = base;
      } catch (_) { /* optional */ }
    }
    await loadPreview(currentMemoId, targets.dealId, extractionOverride, targets.contactId, { resetEdits: true });
    return;
  }

  const targets = currentReviewTargets(ctx);
  await loadPreview(currentMemoId, targets.dealId, null, targets.contactId, { resetEdits: true });
});

// Success done button
document.getElementById('success-done-button')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'DISCARD_MEMO' });
});

// ============================================
// MESSAGE LISTENER (State Updates)
// ============================================
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'AUTH_REQUIRED' || message.type === 'LOGGED_OUT') {
    enterLoggedOut();
    return;
  }
  if (message.type === 'STATE_UPDATED') {
    renderState(message.state);
  }
});

try {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    if (!Object.prototype.hasOwnProperty.call(changes, 'accessToken')) return;
    if (!changes.accessToken.newValue) enterLoggedOut();
  });
} catch { /* ignore */ }

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
  enterLoggedOut();
  await api.clearTokens();
  chrome.runtime.sendMessage({ type: 'LOGOUT' }).catch(() => {});
});

// ============================================
// INIT
// ============================================
async function init() {
  showScreen('loading');
  authStatus = 'unknown';

  const { accessToken } = await api.getTokens();
  if (!accessToken) {
    enterLoggedOut();
    return;
  }

  try {
    const user = await api.getCurrentUser();
    const nameEl = document.getElementById('user-name');
    if (nameEl) nameEl.textContent = firstName(user.full_name) || user.email || '';
    const emailEl = document.getElementById('user-email');
    if (emailEl) emailEl.textContent = user.email;

    markSignedIn();
    const state = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
    const base = state && typeof state === 'object' ? state : { status: 'idle', isRecording: false };
    renderState({ ...base, authenticated: true });
  } catch (e) {
    console.error('[Popup] Init error:', e);
    const { accessToken: stillHasToken } = await api.getTokens();
    const screen = screenForInitFailure(e, { hasToken: Boolean(stillHasToken) });
    const detail = typeof e?.data?.detail === 'string' ? e.data.detail : String(e?.message || '');

    if (screen === 'login') {
      await api.clearTokens().catch(() => {});
      enterLoggedOut();
      return;
    }
    if (screen === 'loading-error') {
      document.getElementById('loading-spinner').style.display = 'none';
      document.getElementById('loading-backend-error').style.display = 'block';
      const titleEl = document.getElementById('loading-error-title');
      const detailEl = document.getElementById('loading-error-detail');
      if (e?.status === 503 || /oauth_client_id|supabase auth|token refresh failed|platform bug/i.test(detail)) {
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
      return;
    }
    // Unknown error (e.g. render bug) with a still-valid token — stay signed in
    markSignedIn();
    renderState({ status: 'idle', isRecording: false });
  }
}

init();
