/**
 * Review-screen routing for the extension popup.
 *
 * The review chrome (header + Discard / Confirm) is visible as soon as
 * status === 'review'. Content lives in sibling sections that start hidden.
 * Route by memo status so that body is never left blank.
 */

const PROCESSING_STATUSES = new Set(['transcribing', 'uploading', 'extracting']);

export function sameMemoId(a, b) {
  if (a == null || b == null || a === '' || b === '') return false;
  return String(a) === String(b);
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
  if (status === 'pending_transcript') {
    return { mode: 'pending_transcript' };
  }
  if (status === 'pending_review' || status === 'approved') {
    return { mode: 'pending_review' };
  }
  if (status === 'failed') {
    return {
      mode: 'pending_transcript',
      failed: true,
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
