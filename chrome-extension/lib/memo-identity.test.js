import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  memoListTitle,
  memoListSubtitle,
  reviewIdsFromMemo,
} from './memo-identity.js';

describe('memoListTitle', () => {
  it('prefers the contact name over the company, even without a HubSpot page', () => {
    const memo = {
      extraction: { contactName: 'Franck Valls', companyName: 'NEURTEK' },
    };
    assert.equal(memoListTitle(memo), 'Franck Valls');
    assert.equal(memoListSubtitle(memo), 'NEURTEK');
  });

  it('uses the preview contact when extraction has no name yet', () => {
    assert.equal(
      memoListTitle({ extraction: {} }, { selected_contact: { name: 'Aritzel Expuru' } }),
      'Aritzel Expuru',
    );
  });
});

describe('reviewIdsFromMemo', () => {
  it('uses the memo contact and skips a deal when the memo is contact-only', () => {
    const ids = reviewIdsFromMemo(
      { hubspotContactId: 'C-franck', extraction: { contactName: 'Franck Valls' } },
      { contactId: 'C-other-page', dealId: 'D-holcim' },
    );
    assert.equal(ids.contactId, 'C-franck');
    assert.equal(ids.dealId, null);
    assert.equal(ids.skipDeal, true);
  });

  it('keeps a deal only when the memo already has one', () => {
    const ids = reviewIdsFromMemo(
      { hubspot_contact_id: 'C1', hubspot_deal_id: 'D1' },
      { dealId: 'D-page' },
    );
    assert.equal(ids.dealId, 'D1');
    assert.equal(ids.skipDeal, false);
  });
});
