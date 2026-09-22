import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  approvePayload,
  isReviewReady,
  notesFromPreview,
  pickDeal,
  waitForReview,
} from './memo-review.js';

describe('memo-review', () => {
  it('auto-selects a confident HubSpot match and asks when confidence is low', () => {
    const auto = pickDeal([
      { deal_id: '1', match_confidence: 0.4 },
      { deal_id: '2', match_confidence: 0.91 },
    ]);
    assert.equal(auto.dealId, '2');
    assert.equal(auto.needsDecision, false);
    const ask = pickDeal([{ deal_id: '1', match_confidence: 0.4 }]);
    assert.equal(ask.dealId, null);
    assert.equal(ask.needsDecision, true);
  });

  it('polls until pending_review', async () => {
    const statuses = ['extracting', 'extracting', 'pending_review'];
    const result = await waitForReview(
      async () => ({ status: statuses.shift() }),
      { intervalMs: 0, timeoutMs: 1000, sleep: async () => {} },
    );
    assert.equal(result.ok, true);
    assert.equal(isReviewReady(result.status), true);
  });

  it('builds the approve body the SaaS expects', () => {
    const payload = approvePayload({
      dealId: 'd1',
      extraction: { summary: 'Recap' },
      contactId: 'c1',
    });
    assert.equal(payload.deal_id, 'd1');
    assert.equal(payload.contact_id, 'c1');
    assert.equal(payload.extraction.summary, 'Recap');
  });

  it('prefers extraction summary for the notes pane', () => {
    const notes = notesFromPreview(
      { transcript_summary: 'clip' },
      { summary: 'Full recap', nextSteps: ['Send deck'] },
    );
    assert.equal(notes.summary, 'Full recap');
    assert.deepEqual(notes.nextSteps, ['Send deck']);
  });
});
