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
