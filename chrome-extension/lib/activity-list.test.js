import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  RECORDINGS_PAGE_SIZE,
  activityEmptyMessage,
  isRecordPageContext,
  nextVisibleCount,
  shouldFetchVocifyMemos,
  shouldShowInboxKicker,
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

  it('uses the inbox copy when there are no recent HubSpot calls', () => {
    assert.equal(
      activityEmptyMessage(null, { recordingsCount: 0, memosCount: 0 }),
      'No recent HubSpot calls.'
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

describe('shouldShowInboxKicker', () => {
  it('is only for inbox with calls or a pending fetch', () => {
    assert.equal(shouldShowInboxKicker(null, { hasRecordings: true }), true);
    assert.equal(shouldShowInboxKicker(null, { loading: true }), true);
    assert.equal(shouldShowInboxKicker(null, {}), false);
    assert.equal(
      shouldShowInboxKicker({ objectType: 'deal', recordId: 'D1' }, { hasRecordings: true }),
      false
    );
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
