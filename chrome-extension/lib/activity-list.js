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
  return true;
}

/** GET /memos is a JSON array; never treat a 200 object as “no memos”. */
export function memoListFromResponse(results) {
  if (Array.isArray(results)) return results;
  if (!results || typeof results !== 'object' || results.error) return [];
  if (Array.isArray(results.items)) return results.items;
  if (Array.isArray(results.data)) return results.data;
  if (Array.isArray(results.memos)) return results.memos;
  return [];
}

function toSortMs(value) {
  if (value == null || value === '') return 0;
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value < 1e12 ? value * 1000 : value;
  }
  const ms = Date.parse(String(value));
  return Number.isFinite(ms) ? ms : 0;
}

export function mergeActivityItems({ recordings = [], memos = [], callMemoIds = null, outboundCalls = [] } = {}) {
  const listed = (recordings || []).filter((r) => r && r.has_recording);
  const ids = callMemoIds instanceof Set
    ? callMemoIds
    : new Set(listed.map((r) => r?.memo_id).filter(Boolean).map(String));

  const calls = listed.map((r) => ({
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

  const outboundSkip = new Set([
    ...ids,
    ...(memos || []).map((m) => m?.id).filter(Boolean).map(String),
  ]);
  const outbound = (outboundCalls || [])
    .filter((c) => c && c.callSid && !(c.memoId && outboundSkip.has(String(c.memoId))))
    .map((c) => ({
      kind: 'outbound',
      id: c.callSid,
      sortMs: toSortMs(c.startedAt || c.answeredAt),
      outbound: c,
    }));

  return [...calls, ...vocify, ...outbound].sort((a, b) => (b.sortMs || 0) - (a.sortMs || 0));
}

function recordingStamp(state) {
  return (state?.recordings || [])
    .filter((r) => r && r.has_recording)
    .map((r) => `${r.call_id || ''}:${r.memo_id || ''}:${r.memo_status || ''}`)
    .join(',');
}

/**
 * Buttons, screens, context strip — anything a hover or click can sit on.
 * Activity rows and live transcript/coaching copy are keyed separately.
 */
export function uiChromeKey(state) {
  const ctx = state?.context || null;
  return [
    state?.status || '',
    state?.isRecording ? '1' : '0',
    state?.isCopilotListening ? '1' : '0',
    state?.listenPhase || '',
    state?.processingSource || '',
    state?.currentMemoId || '',
    state?.copilotError || '',
    ctx?.objectType || '',
    ctx?.recordId || '',
    ctx?.dealName || ctx?.contactName || ctx?.companyName || '',
  ].join('|');
}

/** @deprecated use uiChromeKey — same fingerprint, idle-era name. */
export function idleScreenKey(state) {
  return uiChromeKey(state);
}

export function liveCopyKey(state) {
  const suggestion = state?.copilotSuggestion;
  return [
    state?.finalTranscript || '',
    state?.interimTranscript || '',
    suggestion?.say_this || '',
    suggestion?.next_question || '',
    state?.copilotLastTurn || '',
    state?.copilotIsLoading ? '1' : '0',
    state?.copilotTabTitle || '',
  ].join('|');
}

export function activityListKey(state, { memoStamp = '', visibleCount = 5, memosLoading = false, outboundStamp = '' } = {}) {
  const recs = recordingStamp(state);
  const emptyList = !recs && !memoStamp && !outboundStamp;
  const loading = Boolean(state?.recordingsLoading || memosLoading);
  return [
    recs,
    memoStamp,
    outboundStamp,
    String(visibleCount || 5),
    emptyList && loading ? '1' : '0',
  ].join('|');
}

export function shouldSkipIdlePaint(prevKey, nextKey) {
  return Boolean(prevKey) && prevKey === nextKey;
}

export function nextPaintMode(prevChrome, nextChrome, prevLive, nextLive) {
  if (!prevChrome || prevChrome !== nextChrome) return 'full';
  if (prevLive !== nextLive) return 'live';
  return 'skip';
}
