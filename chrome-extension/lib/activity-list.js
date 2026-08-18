/**
 * Idle activity list: HubSpot calls + Vocify memos, inbox vs record page.
 */

export const RECORDINGS_PAGE_SIZE = 5;

export function isRecordPageContext(context) {
  return Boolean(
    context?.recordId && ['deal', 'contact', 'company'].includes(context.objectType)
  );
}

/** Company memos have no hubspot_company_id column — skip unscoped global memos. */
export function shouldFetchVocifyMemos(context) {
  if (context?.objectType === 'company' && context.recordId) return false;
  return true;
}

export function shouldShowInboxKicker(context, { hasRecordings = false, loading = false } = {}) {
  if (isRecordPageContext(context)) return false;
  return Boolean(hasRecordings || loading);
}

export function activityEmptyMessage(context, {
  recordingsCount = 0,
  memosCount = 0,
  loading = false,
} = {}) {
  if (loading || recordingsCount > 0 || memosCount > 0) return null;
  if (isRecordPageContext(context)) {
    return `No activity on this ${context.objectType} yet.`;
  }
  return 'No recent HubSpot calls.';
}

export function nextVisibleCount(current, total, pageSize = RECORDINGS_PAGE_SIZE) {
  const from = Number(current);
  const start = Number.isFinite(from) && from > 0 ? from : pageSize;
  return Math.min(Math.max(Number(total) || 0, 0), start + pageSize);
}
