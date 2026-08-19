import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  associatedContactsFromContext,
  bindPreviewIds,
  bindPreviewToPage,
  formatSyncTargetLabel,
  needsAssociatedContactPick,
  pickContextTab,
  proposedUpdatesForPage,
  resolveReviewTargets,
} from './review-targets.js';

describe('resolveReviewTargets', () => {
  it('on a contact page uses that contact and does not attach a leftover deal', () => {
    const targets = resolveReviewTargets({
      pageContext: { objectType: 'contact', recordId: 'C-now', companyId: 'CO-1' },
      userDealId: null,
      userContactId: 'C-old',
      previousDealId: 'D-stale',
    });
    assert.equal(targets.contactId, 'C-now');
    assert.equal(targets.dealId, null);
    assert.equal(targets.companyId, 'CO-1');
    assert.equal(targets.skipDeal, true);
  });

  it('on a contact page keeps a deal only when the user explicitly picked it', () => {
    const targets = resolveReviewTargets({
      pageContext: { objectType: 'contact', recordId: 'C-now' },
      userDealId: 'D-picked',
    });
    assert.equal(targets.contactId, 'C-now');
    assert.equal(targets.dealId, 'D-picked');
    assert.equal(targets.skipDeal, false);
  });

  it('on a deal page an explicit search pick replaces the page deal without keeping the old contact', () => {
    const targets = resolveReviewTargets({
      pageContext: { objectType: 'deal', recordId: 'D-page', contactId: 'C-on-page' },
      userDealId: 'D-searched',
    });
    assert.equal(targets.dealId, 'D-searched');
    assert.equal(targets.contactId, null);
    assert.equal(targets.skipDeal, false);
  });

  it('on a deal page uses that deal and this deal’s only contact, not a leftover contact', () => {
    const targets = resolveReviewTargets({
      pageContext: {
        objectType: 'deal',
        recordId: 'D-now',
        contactId: 'C-on-deal',
        companyId: 'CO-1',
        dealContacts: [{ contact_id: 'C-on-deal' }],
      },
      userContactId: null,
      previousContactId: 'C-from-last-page',
      previousDealId: 'D-old',
    });
    assert.equal(targets.dealId, 'D-now');
    assert.equal(targets.contactId, 'C-on-deal');
    assert.equal(targets.companyId, 'CO-1');
    assert.equal(targets.skipDeal, false);
  });

  it('on a deal page with several contacts does not use HubSpot’s first association', () => {
    const targets = resolveReviewTargets({
      pageContext: {
        objectType: 'deal',
        recordId: 'D-now',
        contactId: 'C-first',
        dealContacts: [{ contact_id: 'C-first' }, { contact_id: 'C-second' }],
      },
    });
    assert.equal(targets.dealId, 'D-now');
    assert.equal(targets.contactId, null);
  });

  it('on a deal page with URL-only context does not invent a contact from a previous page', () => {
    const targets = resolveReviewTargets({
      pageContext: { objectType: 'deal', recordId: 'D-now' },
      previousContactId: 'C-from-last-page',
    });
    assert.equal(targets.dealId, 'D-now');
    assert.equal(targets.contactId, null);
  });

  it('on a company page with several contacts does not pick the first one', () => {
    const targets = resolveReviewTargets({
      pageContext: {
        objectType: 'company',
        recordId: 'CO-now',
        companyContacts: [
          { contact_id: 'C-a' },
          { contact_id: 'C-b' },
        ],
      },
    });
    assert.equal(targets.companyId, 'CO-now');
    assert.equal(targets.contactId, null);
    assert.equal(targets.dealId, null);
    assert.equal(targets.skipDeal, true);
  });

  it('on a company page with one associated contact uses that contact', () => {
    const targets = resolveReviewTargets({
      pageContext: {
        objectType: 'company',
        recordId: 'CO-now',
        contactId: 'C-only',
        companyContacts: [{ contact_id: 'C-only' }],
      },
    });
    assert.equal(targets.contactId, 'C-only');
    assert.equal(targets.companyId, 'CO-now');
  });
});

describe('bindPreviewToPage', () => {
  it('drops a previously matched deal when the page is a contact', () => {
    const out = bindPreviewToPage({
      preview: {
        selected_deal: { deal_id: 'D-old', deal_name: 'Old deal' },
        proposed_updates: [
          { object_type: 'deals', field_name: 'amount', new_value: '10' },
          { object_type: 'contacts', field_name: 'phone', new_value: '1' },
        ],
      },
      requestedContactId: 'C-now',
      pageType: 'contact',
    });
    assert.equal(out.selected_deal, null);
    assert.equal(out.skip_deal, true);
    assert.deepEqual(
      proposedUpdatesForPage(out).map((u) => u.field_name),
      ['phone'],
    );
  });

  it('drops the matcher deal when the record was closed (inbox)', () => {
    const out = bindPreviewToPage({
      preview: { selected_deal: { deal_id: 'D-old', deal_name: 'Old deal' } },
      pageType: null,
    });
    assert.equal(out.selected_deal, null);
    assert.equal(out.skip_deal, true);
  });

  it('keeps the deal only when this page requested that deal id', () => {
    const out = bindPreviewToPage({
      preview: { selected_deal: { deal_id: 'D-now', deal_name: 'Now' } },
      requestedDealId: 'D-now',
      pageType: 'deal',
    });
    assert.equal(out.selected_deal.deal_id, 'D-now');
    assert.equal(out.skip_deal, false);
  });
});

describe('bindPreviewIds', () => {
  it('does not adopt a deal the preview invented when none was requested', () => {
    const bound = bindPreviewIds({
      requestedDealId: null,
      requestedContactId: 'C-now',
      preview: {
        selected_deal: { deal_id: 'D-auto' },
        selected_contact: { contact_id: 'C-now', company_id: 'CO-1' },
      },
    });
    assert.equal(bound.dealId, null);
    assert.equal(bound.contactId, 'C-now');
  });

  it('keeps the requested page contact even if preview selected someone else', () => {
    const bound = bindPreviewIds({
      requestedDealId: null,
      requestedContactId: 'C-page',
      preview: {
        selected_contact: { contact_id: 'C-extracted' },
      },
    });
    assert.equal(bound.contactId, 'C-page');
  });

  it('uses the requested deal when preview confirms it', () => {
    const bound = bindPreviewIds({
      requestedDealId: 'D-page',
      requestedContactId: 'C-on-deal',
      preview: {
        selected_deal: { deal_id: 'D-page' },
        selected_contact: { contact_id: 'C-on-deal' },
      },
    });
    assert.equal(bound.dealId, 'D-page');
    assert.equal(bound.contactId, 'C-on-deal');
  });

  it('does not adopt an extraction-matched contact on a deal page when none was requested', () => {
    const bound = bindPreviewIds({
      requestedDealId: 'D-page',
      requestedContactId: null,
      adoptPreviewContact: false,
      preview: {
        selected_deal: { deal_id: 'D-page' },
        selected_contact: { contact_id: 'C-extracted' },
      },
    });
    assert.equal(bound.dealId, 'D-page');
    assert.equal(bound.contactId, null);
  });
});

describe('associated contact pick', () => {
  it('lists deal and company associations without inventing a default', () => {
    assert.deepEqual(
      associatedContactsFromContext({
        objectType: 'deal',
        dealContacts: [{ contact_id: 'A' }, { contact_id: 'B' }],
      }).map((c) => c.contact_id),
      ['A', 'B']
    );
    assert.equal(
      needsAssociatedContactPick(
        { objectType: 'deal', dealContacts: [{ contact_id: 'A' }, { contact_id: 'B' }] },
        null
      ),
      true
    );
    assert.equal(
      needsAssociatedContactPick(
        { objectType: 'deal', dealContacts: [{ contact_id: 'A' }, { contact_id: 'B' }] },
        'A'
      ),
      false
    );
  });
});

describe('formatSyncTargetLabel', () => {
  it('names the records that will actually be written', () => {
    assert.equal(
      formatSyncTargetLabel({ contactName: 'Jane Doe', dealName: 'Acme', skipDeal: false }),
      'Acme · Jane Doe'
    );
    assert.equal(
      formatSyncTargetLabel({ contactName: 'Jane Doe', dealName: null, skipDeal: true }),
      'Jane Doe'
    );
    assert.equal(
      formatSyncTargetLabel({ needsContactPick: true }),
      'Pick a contact first'
    );
  });
});

describe('pickContextTab', () => {
  it('uses the last active tab and does not grab a background HubSpot record', () => {
    const tabs = [
      { id: 1, url: 'https://mail.google.com/mail', active: true },
      { id: 2, url: 'https://app.hubspot.com/contacts/1/record/0-1/999', active: false },
    ];
    const picked = pickContextTab(tabs, { lastActiveTabId: 1 });
    assert.equal(picked.id, 1);
  });

  it('prefers the last active HubSpot record when that is the current tab', () => {
    const tabs = [
      { id: 8, url: 'https://app.hubspot.com/contacts/1/record/0-1/111', active: true },
      { id: 9, url: 'https://app.hubspot.com/contacts/1/record/0-1/222', active: false },
    ];
    const picked = pickContextTab(tabs, { lastActiveTabId: 8 });
    assert.equal(picked.id, 8);
  });

  it('does not keep a closed deal by falling back to a background HubSpot tab', () => {
    const tabs = [
      { id: 9, url: 'https://app.hubspot.com/contacts/1/record/0-3/111', active: false },
      { id: 8, url: 'https://app.hubspot.com/contacts/1/record/0-3/222', active: false },
    ];
    const picked = pickContextTab(tabs, { lastActiveTabId: null });
    assert.equal(picked, null);
  });
});
