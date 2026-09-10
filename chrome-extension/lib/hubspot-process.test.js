import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  crmConfigAutoSyncEnabled,
  decideHubspotCallPollAction,
  decideProcessHubspotCallAction,
} from './hubspot-process.js';

describe('decideProcessHubspotCallAction', () => {
  it('polls while Transcribe is still working', () => {
    for (const status of ['transcribing', 'uploading', 'extracting', 'pending_transcript']) {
      assert.deepEqual(
        decideProcessHubspotCallAction({ memo_id: 'm1', status }),
        { type: 'poll', memoId: 'm1' },
        status,
      );
    }
  });

  it('opens review when the memo is waiting on the SDR', () => {
    assert.deepEqual(
      decideProcessHubspotCallAction({ memo_id: 'm1', status: 'pending_review' }),
      { type: 'review', memoId: 'm1' },
    );
  });

  it('shows success when auto-sync already approved the call', () => {
    assert.deepEqual(
      decideProcessHubspotCallAction({ memo_id: 'm1', status: 'approved' }),
      { type: 'success', memoId: 'm1' },
    );
  });

  it('returns to idle when process failed or there is no memo', () => {
    assert.deepEqual(
      decideProcessHubspotCallAction({ memo_id: 'm1', status: 'failed' }),
      { type: 'failed', memoId: 'm1' },
    );
    assert.deepEqual(decideProcessHubspotCallAction({}), { type: 'idle' });
  });
});

describe('decideHubspotCallPollAction', () => {
  it('opens review immediately when auto-sync is off', () => {
    assert.equal(
      decideHubspotCallPollAction('pending_review', { autoSync: false }).type,
      'review',
    );
  });

  it('waits through pending_review while auto-sync may still approve', () => {
    assert.equal(
      decideHubspotCallPollAction('pending_review', {
        autoSync: true,
        pendingReviewTicks: 0,
      }).type,
      'wait_auto_sync',
    );
    assert.equal(
      decideHubspotCallPollAction('approved', { autoSync: true }).type,
      'success',
    );
  });

  it('falls back to review if auto-sync never approves', () => {
    assert.equal(
      decideHubspotCallPollAction('pending_review', {
        autoSync: true,
        pendingReviewTicks: 15,
      }).type,
      'review',
    );
  });
});

describe('crmConfigAutoSyncEnabled', () => {
  it('is off unless the workspace toggle is on', () => {
    assert.equal(crmConfigAutoSyncEnabled(null), false);
    assert.equal(crmConfigAutoSyncEnabled({}), false);
    assert.equal(crmConfigAutoSyncEnabled({ auto_sync_hubspot_calls: false }), false);
    assert.equal(crmConfigAutoSyncEnabled({ auto_sync_hubspot_calls: true }), true);
  });
});
