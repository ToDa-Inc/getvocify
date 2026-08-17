/**
 * Policy for HubSpot call-memo polling while the user is viewing a record.
 *
 * Opening a contact/deal page must show that record's recordings and memos.
 * It must never hijack the UI into processing/review — that looks like the
 * extension is "recording" and can get stuck on "Converting speech to text…".
 */

export function decideCallWatchAction({
  status,
  memoId,
  baselineMemoId,
  ignoredIds = new Set(),
} = {}) {
  if (!memoId) {
    return {
      autoOpen: false,
      baselineMemoId: baselineMemoId === undefined ? null : baselineMemoId,
    };
  }

  const id = String(memoId);
  if (
    ignoredIds.has(id) ||
    status === 'approved' ||
    status === 'rejected' ||
    status === 'failed' ||
    status === 'waiting'
  ) {
    return { autoOpen: false, baselineMemoId };
  }

  if (baselineMemoId === undefined) {
    return { autoOpen: false, baselineMemoId: id, ignoreId: id };
  }

  return { autoOpen: false, baselineMemoId };
}

/**
 * Opening the side panel must show the current record, not a leftover
 * "Converting speech to text…" screen. Back already does this via DISCARD_MEMO.
 * Keep a live mic session; keep review because the user is already in that flow.
 */
export function panelOpenState(state) {
  if (!state || typeof state !== 'object') {
    return { status: 'idle', isRecording: false };
  }
  if (state.isRecording) return state;
  if (state.status === 'processing') {
    return {
      ...state,
      status: 'idle',
      processingSource: null,
    };
  }
  return state;
}
