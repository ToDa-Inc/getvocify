import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  RECORDINGS_PAGE_SIZE,
  activityEmptyMessage,
  activityKickerLabel,
  isRecordPageContext,
  isVocifyMemo,
  memoListFromResponse,
  mergeActivityItems,
  nextVisibleCount,
  shouldFetchVocifyMemos,
  shouldShowActivityKicker,
  idleScreenKey,
  shouldSkipIdlePaint,
  uiChromeKey,
  liveCopyKey,
  activityListKey,
  nextPaintMode,
} from './activity-list.js';

describe('isRecordPageContext', () => {
  it('is true for deal, contact, and company records', () => {
    assert.equal(isRecordPageContext({ objectType: 'deal', recordId: 'D1' }), true);
    assert.equal(isRecordPageContext({ objectType: 'contact', recordId: 'C1' }), true);
    assert.equal(isRecordPageContext({ objectType: 'company', recordId: 'CO1' }), true);
  });

  it('is false for inbox (no record)', () => {
    assert.equal(isRecordPageContext(null), false);
    assert.equal(isRecordPageContext({ objectType: 'deal' }), false);
  });
});

describe('shouldFetchVocifyMemos', () => {
  it('skips unscoped memos on a company page', () => {
    assert.equal(shouldFetchVocifyMemos({ objectType: 'company', recordId: 'CO1' }), false);
  });

  it('fetches memos on contact, deal, and inbox', () => {
    assert.equal(shouldFetchVocifyMemos({ objectType: 'contact', recordId: 'C1' }), true);
    assert.equal(shouldFetchVocifyMemos({ objectType: 'deal', recordId: 'D1' }), true);
    assert.equal(shouldFetchVocifyMemos(null), true);
  });
});

describe('activityEmptyMessage', () => {
  it('names the record type when a contact/deal/company has no activity', () => {
    assert.equal(
      activityEmptyMessage({ objectType: 'contact', recordId: 'C1' }, { recordingsCount: 0, memosCount: 0 }),
      'No activity on this contact yet.'
    );
    assert.equal(
      activityEmptyMessage({ objectType: 'deal', recordId: 'D1' }, { recordingsCount: 0, memosCount: 0 }),
      'No activity on this deal yet.'
    );
    assert.equal(
      activityEmptyMessage({ objectType: 'company', recordId: 'CO1' }, { recordingsCount: 0, memosCount: 0 }),
      'No activity on this company yet.'
    );
  });

  it('uses the inbox copy when there is no activity', () => {
    assert.equal(
      activityEmptyMessage(null, { recordingsCount: 0, memosCount: 0 }),
      'No activity yet.'
    );
  });

  it('is silent while loading or when anything is listed', () => {
    assert.equal(activityEmptyMessage(null, { loading: true }), null);
    assert.equal(activityEmptyMessage(null, { recordingsCount: 1 }), null);
    assert.equal(
      activityEmptyMessage({ objectType: 'deal', recordId: 'D1' }, { memosCount: 1 }),
      null
    );
  });
});

describe('shouldShowActivityKicker', () => {
  it('is only for inbox when there is activity or a pending fetch', () => {
    assert.equal(shouldShowActivityKicker(null, { itemCount: 1 }), true);
    assert.equal(shouldShowActivityKicker(null, { loading: true }), true);
    assert.equal(shouldShowActivityKicker(null, {}), false);
    assert.equal(
      shouldShowActivityKicker({ objectType: 'deal', recordId: 'D1' }, { itemCount: 3 }),
      false
    );
  });
});

describe('activityKickerLabel', () => {
  it('does not pretend memos are calls', () => {
    assert.equal(activityKickerLabel(), 'Activity');
  });
});

describe('isVocifyMemo', () => {
  it('drops a memo only when that call is already in the activity list', () => {
    const callIds = new Set(['m1']);
    assert.equal(isVocifyMemo({ id: 'm1' }, callIds), false);
    assert.equal(isVocifyMemo({ id: 'm2', source: 'hubspot_call' }, callIds), true);
    assert.equal(isVocifyMemo({ id: 'm4', source: 'voice' }, callIds), true);
  });
});

describe('memoListFromResponse', () => {
  it('keeps a JSON array from GET /memos', () => {
    assert.equal(memoListFromResponse([{ id: 'm1' }]).length, 1);
    assert.deepEqual(memoListFromResponse({ items: [{ id: 'm1' }] }), [{ id: 'm1' }]);
    assert.deepEqual(memoListFromResponse({ error: 'nope' }), []);
  });
});

describe('mergeActivityItems', () => {
  it('mixes calls and memos newest first and skips recordings without audio', () => {
    const items = mergeActivityItems({
      recordings: [
        { call_id: 'c-old', has_recording: true, timestamp: '2026-08-01T10:00:00.000Z', title: 'Old call' },
        { call_id: 'c-skip', has_recording: false, timestamp: '2026-08-19T10:00:00.000Z' },
        { call_id: 'c-new', memo_id: 'dup', has_recording: true, timestamp_ms: Date.parse('2026-08-18T12:00:00.000Z'), title: 'New call' },
      ],
      memos: [
        { id: 'memo-mid', created_at: '2026-08-10T09:00:00.000Z', source: 'voice' },
        { id: 'dup', created_at: '2026-08-19T09:00:00.000Z', source: 'hubspot_call' },
      ],
    });
    assert.deepEqual(items.map((i) => i.id), ['c-new', 'memo-mid', 'c-old']);
    assert.deepEqual(items.map((i) => i.kind), ['call', 'memo', 'call']);
  });

  it('still lists a HubSpot call memo when there is no playable recording', () => {
    const items = mergeActivityItems({
      recordings: [
        { call_id: 'c1', memo_id: 'm-hs', has_recording: false, timestamp: '2026-08-19T10:00:00.000Z' },
      ],
      memos: [
        { id: 'm-hs', created_at: '2026-08-19T10:00:00.000Z', source: 'hubspot_call' },
      ],
    });
    assert.deepEqual(items.map((i) => i.id), ['m-hs']);
    assert.equal(items[0].kind, 'memo');
  });
});

describe('nextVisibleCount', () => {
  it('shows 5 then adds 5 up to the fetched total', () => {
    assert.equal(RECORDINGS_PAGE_SIZE, 5);
    assert.equal(nextVisibleCount(5, 20), 10);
    assert.equal(nextVisibleCount(10, 20), 15);
    assert.equal(nextVisibleCount(15, 20), 20);
    assert.equal(nextVisibleCount(20, 20), 20);
  });
});

describe('idleScreenKey', () => {
  it('stays the same when only captureTabId or authenticated changes', () => {
    const base = {
      status: 'idle',
      isRecording: false,
      recordings: [{ call_id: 'c1', has_recording: true, memo_status: null }],
      context: null,
    };
    assert.equal(
      idleScreenKey(base),
      idleScreenKey({ ...base, captureTabId: 12, authenticated: true }),
    );
  });

  it('does not rebuild idle chrome when a call memo status changes', () => {
    const rec = { call_id: 'c1', has_recording: true, memo_status: null };
    const before = idleScreenKey({ status: 'idle', recordings: [rec], context: null });
    const after = idleScreenKey({
      status: 'idle',
      recordings: [{ ...rec, memo_status: 'pending_review', memo_id: 'm1' }],
      context: null,
    });
    assert.equal(before, after);
  });
});

describe('shouldSkipIdlePaint', () => {
  it('skips a full idle repaint when nothing visible changed', () => {
    assert.equal(shouldSkipIdlePaint('idle|x', 'idle|x'), true);
    assert.equal(shouldSkipIdlePaint('idle|x', 'idle|y'), false);
    assert.equal(shouldSkipIdlePaint(null, 'idle|x'), false);
  });
});

describe('uiChromeKey', () => {
  const idle = {
    status: 'idle',
    isRecording: false,
    recordings: [{ call_id: 'c1', has_recording: true, memo_status: null }],
    context: null,
  };

  it('is the idle screen key, so existing skip logic still applies', () => {
    assert.equal(uiChromeKey(idle), idleScreenKey(idle));
  });

  it('ignores live transcript so Listen/Record chrome is not rebuilt every STT tick', () => {
    assert.equal(
      uiChromeKey({ ...idle, isRecording: true, status: 'recording', finalTranscript: 'hi' }),
      uiChromeKey({ ...idle, isRecording: true, status: 'recording', finalTranscript: 'hi there', interimTranscript: 'now' }),
    );
  });

  it('ignores activity loading and rows so Transcribe hover survives list updates', () => {
    assert.equal(
      uiChromeKey({ ...idle, recordingsLoading: true }),
      uiChromeKey({ ...idle, recordingsLoading: false }),
    );
    const empty = { status: 'idle', recordings: [], context: null };
    assert.equal(
      uiChromeKey({ ...empty, recordingsLoading: true }),
      uiChromeKey({ ...empty, recordingsLoading: false }),
    );
  });

  it('changes when review/processing identity changes', () => {
    assert.notEqual(
      uiChromeKey({ status: 'processing', processingSource: 'voice' }),
      uiChromeKey({ status: 'processing', processingSource: 'hubspot_call' }),
    );
    assert.notEqual(
      uiChromeKey({ status: 'review', currentMemoId: 'm1' }),
      uiChromeKey({ status: 'review', currentMemoId: 'm2' }),
    );
  });
});

describe('liveCopyKey', () => {
  it('changes when transcript or copilot coaching copy changes', () => {
    const base = { finalTranscript: 'a', copilotSuggestion: { say_this: 'Ask budget' } };
    assert.notEqual(liveCopyKey(base), liveCopyKey({ ...base, interimTranscript: 'b' }));
    assert.notEqual(
      liveCopyKey(base),
      liveCopyKey({ ...base, copilotSuggestion: { say_this: 'Ask timeline' } }),
    );
  });
});

describe('activityListKey', () => {
  const recs = [{ call_id: 'c1', has_recording: true, memo_status: null }];

  it('ignores watch phase so the list rows are not remounted', () => {
    assert.equal(
      activityListKey({ recordings: recs, watchPhase: 'awaiting_recording' }, { visibleCount: 5 }),
      activityListKey({ recordings: recs, watchPhase: 'recording_found' }, { visibleCount: 5 }),
    );
  });

  it('changes when Show more expands or a memo lands', () => {
    const state = { recordings: recs };
    assert.notEqual(
      activityListKey(state, { visibleCount: 5 }),
      activityListKey(state, { visibleCount: 10 }),
    );
    assert.notEqual(
      activityListKey(state, { memoStamp: '' }),
      activityListKey(state, { memoStamp: 'm1:pending_review' }),
    );
  });

  it('tracks empty-list loading and call memo status without using watch phase', () => {
    const empty = { recordings: [], recordingsLoading: true };
    assert.notEqual(
      activityListKey(empty, { memoStamp: '' }),
      activityListKey({ recordings: [], recordingsLoading: false }, { memoStamp: '' }),
    );
    const rec = { call_id: 'c1', has_recording: true, memo_status: null };
    assert.notEqual(
      activityListKey({ recordings: [rec] }),
      activityListKey({ recordings: [{ ...rec, memo_status: 'pending_review', memo_id: 'm1' }] }),
    );
  });
});

describe('nextPaintMode', () => {
  it('skips, patches live copy, or fully paints', () => {
    assert.equal(nextPaintMode(null, 'chrome', null, 'live'), 'full');
    assert.equal(nextPaintMode('chrome', 'chrome', 'live', 'live'), 'skip');
    assert.equal(nextPaintMode('chrome', 'chrome', 'live', 'live2'), 'live');
    assert.equal(nextPaintMode('chrome', 'chrome2', 'live', 'live'), 'full');
  });
});
