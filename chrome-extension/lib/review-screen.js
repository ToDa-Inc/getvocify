/**
 * Review-screen routing for the extension popup.
 *
 * The review chrome (header + Discard / Confirm) is visible as soon as
 * status === 'review'. Content lives in sibling sections that start hidden.
 * Route by memo status so that body is never left blank.
 */

const PROCESSING_STATUSES = new Set(['transcribing', 'uploading', 'extracting', 'pending_transcript']);

export function sameMemoId(a, b) {
  if (a == null || b == null || a === '' || b === '') return false;
  return String(a) === String(b);
}

/** Cached review payload is only valid for this memo — never paint the previous call. */
export function reviewMemoIfCurrent(reviewMemo, memoId) {
  if (!reviewMemo) return null;
  const id = reviewMemo.id ?? reviewMemo.memo_id;
  return sameMemoId(id, memoId) ? reviewMemo : null;
}

/**
 * Fill the call note from a memo. A different call always replaces.
 * The same call only fills an empty box so tab/preview refreshes keep edits.
 */
export function shouldWriteCallNote({
  memoId = null,
  paintedMemoId = null,
  existingText = '',
  incomingText = '',
} = {}) {
  if (!String(incomingText || '').trim()) return false;
  if (!sameMemoId(memoId, paintedMemoId)) return true;
  return !String(existingText || '').trim();
}

/**
 * Once Review & sync is open for a memo, keep that preview until
 * discard/approve — do not follow HubSpot tab changes.
 */
export function shouldReloadReviewPreview({
  memoId = null,
  loadedMemoId = null,
  pageKey = null,
  loadedPageKey = null,
  sessionLocked = false,
} = {}) {
  if (!sameMemoId(memoId, loadedMemoId)) return true;
  if (sessionLocked) return false;
  return String(pageKey || '') !== String(loadedPageKey || '');
}

/**
 * Review binds to the process at open — including the inbox, which has no
 * HubSpot recordId. A later focused contact/deal table must not steal it.
 */
export function planReviewSessionLock({ alreadyLocked = false, liveContext = null } = {}) {
  if (alreadyLocked) return { shouldLock: false };
  return { shouldLock: true, context: liveContext || {} };
}

const NOISE_MATCH_REASONS = new Set([
  'linked to matched contact',
  'manual selection',
  'explicit contact selection',
]);

/** Drop matcher jargon; keep reasons that actually help pick a deal. */
export function dealMatchSubtitle(matchReason) {
  const raw = String(matchReason || '').trim();
  if (!raw) return '';
  return NOISE_MATCH_REASONS.has(raw.toLowerCase()) ? '' : raw;
}

export function dealTargetCardCopy({
  selectedDeal = null,
  skipDeal = false,
  createNewDeal = false,
  pageDeal = false,
} = {}) {
  if (selectedDeal) {
    return {
      title: selectedDeal.deal_name || 'Deal',
      reason: pageDeal ? 'This HubSpot deal' : 'On this contact',
    };
  }
  if (skipDeal) {
    return {
      title: 'Contact only',
      reason: 'No deal will be updated',
    };
  }
  if (createNewDeal) {
    return {
      title: 'New deal',
      reason: 'Created when you sync',
    };
  }
  return {
    title: 'No deal selected',
    reason: 'Optional — pick one if this call belongs on a deal',
  };
}

/**
 * Collapsed: one selected target card.
 * Open: compact picker (contact only + linked deals + create).
 */
export function contactTargetCardCopy({
  selectedContact = null,
  fallbackName = '',
  fallbackMeta = '',
} = {}) {
  if (selectedContact) {
    return {
      title: selectedContact.name || selectedContact.email || 'Contact',
      reason: [selectedContact.email, selectedContact.phone, selectedContact.company_name]
        .filter(Boolean)
        .join(' · '),
      known: true,
      locked: true,
    };
  }
  const name = String(fallbackName || '').trim();
  if (name) {
    return {
      title: name,
      reason: String(fallbackMeta || '').trim(),
      known: true,
      locked: false,
    };
  }
  return {
    title: 'No contact selected',
    reason: 'Search to pick who to update',
    known: false,
    locked: false,
  };
}

/** Search stays closed when the call already has a contact name. */
export function contactPickerVisibility({
  pickerOpen = false,
  hasDisplayContact = false,
} = {}) {
  const showPicker = pickerOpen || !hasDisplayContact;
  return {
    showPicker,
    showCard: !showPicker && hasDisplayContact,
    showSearch: showPicker,
    showChange: hasDisplayContact,
  };
}

export function dealPickerVisibility({
  pickerOpen = false,
  needsConfirm = false,
  hasMatches = false,
  hasSelectedContact = false,
} = {}) {
  const showPicker = pickerOpen || needsConfirm;
  return {
    showPicker,
    showCard: !showPicker,
    showSearch: showPicker && !hasMatches,
    showContactOnlyRow: showPicker && !!hasSelectedContact,
    hint: needsConfirm && !hasSelectedContact
      ? 'Pick a deal before syncing, or create a new one.'
      : 'A deal is optional — this can stay on the contact.',
  };
}

/**
 * @returns {'processing' | 'pending_transcript' | 'pending_review' | 'login' | 'error'}
 */
export function resolveReviewPresentation({ memo = null, error = null, isAuthFailure = null } = {}) {
  if (error) {
    const authFail = typeof isAuthFailure === 'function'
      ? isAuthFailure(error)
      : Number(error.status) === 401;
    if (authFail) return { mode: 'login' };
    const detail = typeof error.data?.detail === 'string' ? error.data.detail : '';
    return {
      mode: 'error',
      message: detail || error.message || 'Could not load this review.',
    };
  }

  const status = String(memo?.status || '');
  if (PROCESSING_STATUSES.has(status)) {
    return { mode: 'processing' };
  }
  if (status === 'pending_review' || status === 'approved') {
    return { mode: 'pending_review' };
  }
  if (status === 'failed') {
    return {
      mode: 'failed',
      message: memo.errorMessage || memo.error_message || 'Extraction failed. Click Retry to try again.',
    };
  }
  return {
    mode: 'error',
    message: status
      ? `This memo is not ready for review (${status.replace(/_/g, ' ')}).`
      : 'Could not load this review.',
  };
}

/**
 * Second full-page spinner after "Getting the transcript" feels stuck.
 * Review chrome should paint immediately; HubSpot matching fills in after.
 */
export function shouldShowReviewOpeningSpinner(_args = {}) {
  return false;
}

export function dealCardWhilePreviewLoads({ pageType = null, pageDealName = '' } = {}) {
  const name = String(pageDealName || '').trim();
  if (pageType === 'deal' && name) {
    return { title: name, reason: 'This HubSpot deal', pending: false };
  }
  return { ...dealTargetCardCopy({}), pending: true };
}

export function canPaintInsightsFromMemo(memo) {
  const ext = memo?.extraction;
  if (!ext || typeof ext !== 'object') return false;
  if (String(ext.summary || '').trim()) return true;
  return Array.isArray(ext.nextSteps) && ext.nextSteps.some((s) => String(s || '').trim());
}

export function slimReviewMemo(memo) {
  if (!memo || typeof memo !== 'object') return null;
  return {
    id: memo.id ?? memo.memo_id ?? null,
    status: memo.status || '',
    extraction: memo.extraction || null,
    transcript: memo.transcript || '',
    hubspotContactId: memo.hubspotContactId || memo.hubspot_contact_id || null,
    hubspotDealId: memo.hubspotDealId || memo.hubspot_deal_id || memo.matchedDealId || memo.matched_deal_id || null,
    errorMessage: memo.errorMessage || memo.error_message || null,
  };
}

export function reviewFieldsSkeletonHtml() {
  return `<div class="review-skel" aria-hidden="true">
    <div class="review-skel-line"></div>
    <div class="review-skel-line"></div>
    <div class="review-skel-line review-skel-line--short"></div>
  </div>`;
}

/**
 * Footer CTA stays short so the label can center.
 * The record name already lives on the deal/contact card above.
 */
export function approveCtaLabel({
  skipDeal = false,
  isNewDeal = false,
  hasDeal = false,
  hasContact = false,
} = {}) {
  if (isNewDeal) return 'Create deal';
  if (skipDeal && hasContact && !hasDeal) return 'Update contact';
  if (hasDeal) return 'Update deal';
  if (hasContact) return 'Update contact';
  return 'Update CRM';
}

/** Full name for hover; not painted in the button. */
export function approveCtaTitle({ skipDeal = false, contactName = '', dealName = '' } = {}) {
  if (skipDeal && contactName) return String(contactName);
  if (dealName) return String(dealName);
  if (contactName) return String(contactName);
  return '';
}

const CONFIRM_TRANSCRIPT_DONE = new Set(['extracting', 'pending_review', 'approved']);

export function confirmTranscriptAlreadyFinished(status) {
  return CONFIRM_TRANSCRIPT_DONE.has(String(status || ''));
}

export function confirmTranscriptErrorStatus(error) {
  const detail = String(error?.data?.detail || error?.message || '');
  const match = detail.match(/Status:\s*([a-z_]+)/i);
  return match ? match[1] : null;
}

/** Live GET wins so a stale pending_transcript cache cannot reopen Extract. */
export function memoForReviewPresentation({ cached = null, fetched = null } = {}) {
  if (fetched && typeof fetched === 'object') return fetched;
  return cached || null;
}

export const TRANSCRIPT_POLISH_WINDOW_MS = 25000;

function latestStageAt(stages, name) {
  let best = 0;
  for (const stage of stages || []) {
    if (stage?.name !== name) continue;
    const t = Date.parse(stage.at || '') || 0;
    if (t > best) best = t;
  }
  return best;
}

export function transcriptPolishSettled(memo) {
  const meta = memo?.pipelineMeta || memo?.pipeline_meta || {};
  const stages = meta.stages || [];
  const extractAt = latestStageAt(stages, 'extract');
  const sanitizeAt = latestStageAt(stages, 'sanitize');
  return extractAt > 0 && sanitizeAt >= extractAt;
}

/** Poll through processing, then a short window so background polish can replace cheap STT. */
export function shouldPollMemo(memo, now = Date.now(), polishWindowMs = TRANSCRIPT_POLISH_WINDOW_MS) {
  const status = memo?.status || '';
  if (['uploading', 'transcribing', 'extracting', 'pending_transcript'].includes(status)) {
    return true;
  }
  if (status !== 'pending_review') return false;
  if (transcriptPolishSettled(memo)) return false;
  const processed = Date.parse(memo?.processedAt || memo?.processed_at || '') || 0;
  if (!processed) return true;
  return now - processed < polishWindowMs;
}
