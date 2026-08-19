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

export function activityKickerLabel() {
  return 'Activity';
}

export function shouldShowActivityKicker(context, { itemCount = 0, loading = false } = {}) {
  if (isRecordPageContext(context)) return false;
  return Boolean(itemCount > 0 || loading);
}

/** @deprecated use shouldShowActivityKicker */
export function shouldShowInboxKicker(context, { hasRecordings = false, loading = false, itemCount = 0 } = {}) {
  return shouldShowActivityKicker(context, {
    itemCount: itemCount || (hasRecordings ? 1 : 0),
    loading,
  });
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
  return 'No activity yet.';
}

export function nextVisibleCount(current, total, pageSize = RECORDINGS_PAGE_SIZE) {
  const from = Number(current);
  const start = Number.isFinite(from) && from > 0 ? from : pageSize;
  return Math.min(Math.max(Number(total) || 0, 0), start + pageSize);
}

export function isVocifyMemo(memo, callIds) {
  const id = memo?.id != null ? String(memo.id) : '';
  if (id && callIds instanceof Set && callIds.has(id)) return false;
  const src = memo?.source || memo?.source_type;
  if (src === 'hubspot_call') return false;
  if (memo?.hubspot_engagement_id) return false;
  return true;
}

function toSortMs(value) {
  if (value == null || value === '') return 0;
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value < 1e12 ? value * 1000 : value;
  }
  const ms = Date.parse(String(value));
  return Number.isFinite(ms) ? ms : 0;
}

export function mergeActivityItems({ recordings = [], memos = [], callMemoIds = null } = {}) {
  const ids = callMemoIds instanceof Set
    ? callMemoIds
    : new Set((recordings || []).map((r) => r?.memo_id).filter(Boolean).map(String));

  const calls = (recordings || [])
    .filter((r) => r && r.has_recording)
    .map((r) => ({
      kind: 'call',
      id: r.call_id,
      sortMs: toSortMs(r.timestamp || r.timestamp_ms),
      recording: r,
    }));

  const vocify = (memos || [])
    .filter((m) => isVocifyMemo(m, ids))
    .map((m) => ({
      kind: 'memo',
      id: m?.id,
      sortMs: toSortMs(m?.createdAt || m?.created_at),
      memo: m,
    }));

  return [...calls, ...vocify].sort((a, b) => (b.sortMs || 0) - (a.sortMs || 0));
}
