import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  RECORDINGS_PAGE_SIZE,
  activityEmptyMessage,
  activityKickerLabel,
  isRecordPageContext,
  isVocifyMemo,
  mergeActivityItems,
  nextVisibleCount,
  shouldFetchVocifyMemos,
  shouldShowActivityKicker,
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
  it('drops HubSpot call memos so they are not listed twice', () => {
    const callIds = new Set(['m1']);
    assert.equal(isVocifyMemo({ id: 'm1' }, callIds), false);
    assert.equal(isVocifyMemo({ id: 'm2', source: 'hubspot_call' }, callIds), false);
    assert.equal(isVocifyMemo({ id: 'm3', hubspot_engagement_id: 'e1' }, callIds), false);
    assert.equal(isVocifyMemo({ id: 'm4', source: 'voice' }, callIds), true);
  });
});

describe('mergeActivityItems', () => {
  it('mixes calls and memos newest first and skips recordings without audio', () => {
    const items = mergeActivityItems({
      recordings: [
        { call_id: 'c-old', has_recording: true, timestamp: '2026-08-01T10:00:00.000Z', title: 'Old call' },
        { call_id: 'c-skip', has_recording: false, timestamp: '2026-08-19T10:00:00.000Z' },
        { call_id: 'c-new', has_recording: true, timestamp_ms: Date.parse('2026-08-18T12:00:00.000Z'), title: 'New call' },
      ],
      memos: [
        { id: 'memo-mid', created_at: '2026-08-10T09:00:00.000Z', source: 'voice' },
        { id: 'dup', created_at: '2026-08-19T09:00:00.000Z', source: 'hubspot_call' },
      ],
    });
    assert.deepEqual(items.map((i) => i.id), ['c-new', 'memo-mid', 'c-old']);
    assert.deepEqual(items.map((i) => i.kind), ['call', 'memo', 'call']);
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
