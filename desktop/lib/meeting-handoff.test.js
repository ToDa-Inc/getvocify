import test from 'node:test';
import assert from 'node:assert/strict';
import { approvePayload, isReviewReady, waitForReview } from './memo-review.js';

test('meeting memo reaches pending_review then builds the CRM approve payload', async () => {
  assert.equal(isReviewReady('pending_review'), true);
  const waited = await waitForReview(
    async () => ({ status: 'pending_review' }),
    { intervalMs: 0, timeoutMs: 500, sleep: async () => {} },
  );
  assert.equal(waited.ok, true);
  const payload = approvePayload({
    dealId: 'deal-1',
    extraction: { summary: 'Recap de la reunión' },
    contactId: 'contact-1',
  });
  assert.equal(payload.deal_id, 'deal-1');
  assert.equal(payload.contact_id, 'contact-1');
  assert.equal(payload.extraction.summary, 'Recap de la reunión');
});
