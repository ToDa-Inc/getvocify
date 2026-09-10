/**
 * Route the HubSpot Transcribe POST and in-flight poll.
 *
 * Auto-sync (opt-in) writes pending_review then approves in the same job.
 * Transcribe must not stick on processing if the memo is already approved,
 * and must not flash Review while that approve is still in flight.
 */

const POLL_STATUSES = new Set([
  'transcribing',
  'uploading',
  'extracting',
  'pending_transcript',
]);

/** Extra poll ticks to wait on pending_review when auto-sync is on (~2s each). */
export const AUTO_SYNC_REVIEW_WAIT_TICKS = 15;

export function crmConfigAutoSyncEnabled(config) {
  return Boolean(config && config.auto_sync_hubspot_calls);
}

export function decideProcessHubspotCallAction(res) {
  const memoId = res?.memo_id != null && String(res.memo_id) ? String(res.memo_id) : null;
  if (!memoId) return { type: 'idle' };
  const status = String(res.status || '');
  if (POLL_STATUSES.has(status)) return { type: 'poll', memoId };
  if (status === 'pending_review') return { type: 'review', memoId };
  if (status === 'approved') return { type: 'success', memoId };
  if (status === 'failed' || status === 'rejected') return { type: 'failed', memoId };
  return { type: 'poll', memoId };
}

export function decideHubspotCallPollAction(
  status,
  { autoSync = false, pendingReviewTicks = 0 } = {},
) {
  const st = String(status || '');
  if (st === 'pending_transcript') return { type: 'confirm_transcript' };
  if (st === 'approved') return { type: 'success' };
  if (st === 'failed' || st === 'rejected') return { type: 'failed' };
  if (st === 'pending_review') {
    if (autoSync && pendingReviewTicks < AUTO_SYNC_REVIEW_WAIT_TICKS) {
      return { type: 'wait_auto_sync' };
    }
    return { type: 'review' };
  }
  return { type: 'continue' };
}
