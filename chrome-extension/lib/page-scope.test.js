import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  hydrateFromIdentityCache,
  identityCacheFromEntries,
  identityCacheToEntries,
  keepReviewSessionContext,
  mergePageContext,
  planContextEnrich,
  planPageContextUpdate,
  recordScopeKey,
  recordingsScopeKey,
  rememberIdentity,
} from './page-scope.js';

describe('recordScopeKey', () => {
  it('keys by object type and id', () => {
    assert.equal(recordScopeKey({ objectType: 'deal', recordId: 'D1' }), 'deal:D1');
    assert.equal(recordScopeKey({ objectType: 'contact', recordId: 'C1' }), 'contact:C1');
  });

  it('is null without a record', () => {
    assert.equal(recordScopeKey(null), null);
    assert.equal(recordScopeKey({ objectType: 'deal' }), null);
  });
});

describe('recordingsScopeKey', () => {
  it('uses inbox when there is no CRM record', () => {
    assert.equal(recordingsScopeKey(null), 'inbox');
    assert.equal(recordingsScopeKey({ objectType: 'deal', recordId: 'D1' }), 'deal:D1');
    assert.equal(recordingsScopeKey({ objectType: 'company', recordId: 'CO1' }), 'company:CO1');
  });
});

describe('mergePageContext', () => {
  it('keeps the enriched name when the same deal is re-applied from the URL', () => {
    const prev = {
      objectType: 'deal',
      recordId: 'D1',
      dealName: 'Drive Solutions Deal',
      contactPhone: '+34600111222',
      _enrichedKey: 'deal:D1',
    };
    const next = { objectType: 'deal', recordId: 'D1', region: 'eu1' };
    const { sameRecord, context } = mergePageContext(prev, next);
    assert.equal(sameRecord, true);
    assert.equal(context.dealName, 'Drive Solutions Deal');
    assert.equal(context.contactPhone, '+34600111222');
    assert.equal(context.region, 'eu1');
    assert.equal(context._enrichedKey, 'deal:D1');
  });

  it('drops the previous deal when the page is a different record', () => {
    const prev = {
      objectType: 'deal',
      recordId: 'D1',
      dealName: 'Drive Solutions Deal',
    };
    const next = { objectType: 'contact', recordId: 'C2' };
    const { sameRecord, context } = mergePageContext(prev, next);
    assert.equal(sameRecord, false);
    assert.equal(context.recordId, 'C2');
    assert.equal(context.dealName, undefined);
  });

  it('drops the name when switching from one deal to another deal', () => {
    const prev = { objectType: 'deal', recordId: 'D1', dealName: 'Acme' };
    const next = { objectType: 'deal', recordId: 'D2' };
    const { sameRecord, context } = mergePageContext(prev, next);
    assert.equal(sameRecord, false);
    assert.equal(context.recordId, 'D2');
    assert.equal(context.dealName, undefined);
  });

  it('clears context when leaving HubSpot', () => {
    const prev = { objectType: 'deal', recordId: 'D1', dealName: 'Acme' };
    const { sameRecord, context } = mergePageContext(prev, null);
    assert.equal(sameRecord, false);
    assert.equal(context, null);
  });
});

describe('planPageContextUpdate', () => {
  it('broadcasts immediately when closing a deal or switching records', () => {
    const deal = { objectType: 'deal', recordId: 'D1', dealName: 'Acme' };
    const other = { objectType: 'deal', recordId: 'D2' };
    assert.equal(planPageContextUpdate(deal, other).skipBroadcast, false);
    assert.equal(planPageContextUpdate(deal, null).skipBroadcast, false);
    assert.equal(planPageContextUpdate(deal, other).replaceLists, true);
  });

  it('skips a no-op when the same deal is still in the address bar', () => {
    const deal = { objectType: 'deal', recordId: 'D1', dealName: 'Acme' };
    const urlOnly = { objectType: 'deal', recordId: 'D1', region: 'eu1' };
    const plan = planPageContextUpdate(deal, urlOnly);
    assert.equal(plan.skipBroadcast, true);
    assert.equal(plan.context.dealName, 'Acme');
  });

  it('does not keep rebroadcasting the inbox', () => {
    assert.equal(planPageContextUpdate(null, null).skipBroadcast, true);
    assert.equal(planPageContextUpdate({ objectType: 'deal' }, { hubId: '1' }).skipBroadcast, true);
  });
});

describe('planContextEnrich', () => {
  it('skips when already enriched or in flight for this record', () => {
    assert.equal(planContextEnrich({ scopeKey: 'contact:1', enrichedKey: 'contact:1' }).action, 'skip');
    assert.equal(planContextEnrich({
      scopeKey: 'contact:1',
      enrichedKey: null,
      inFlightKey: 'contact:1',
    }).action, 'skip');
  });

  it('fetches once when the URL record has no names yet', () => {
    assert.equal(planContextEnrich({ scopeKey: 'contact:1' }).action, 'fetch');
    assert.equal(planContextEnrich({}).action, 'skip');
  });
});

describe('keepReviewSessionContext', () => {
  it('keeps an inbox review on the process when a later HubSpot deal is focused', () => {
    const locked = {};
    const focused = { objectType: 'deal', recordId: 'D-table', dealName: 'Focused row' };
    const kept = keepReviewSessionContext(locked, focused);
    assert.equal(kept.recordId, undefined);
    assert.equal(kept.objectType, undefined);
  });

  it('still merges names when the same locked record is re-enriched', () => {
    const locked = { objectType: 'contact', recordId: 'C1' };
    const enriched = { objectType: 'contact', recordId: 'C1', contactName: 'Franck' };
    const kept = keepReviewSessionContext(locked, enriched);
    assert.equal(kept.contactName, 'Franck');
    assert.equal(kept.recordId, 'C1');
  });
});

describe('identity cache', () => {
  it('hydrates a URL-only contact from a previous visit to that same record', () => {
    const cache = rememberIdentity(new Map(), {
      objectType: 'contact',
      recordId: 'C2',
      contactName: 'Andreea Mora',
      contactPhone: '+34669701069',
    });
    const urlOnly = { objectType: 'contact', recordId: 'C2', hubId: '1', region: 'eu1' };
    const hydrated = hydrateFromIdentityCache(urlOnly, cache);
    assert.equal(hydrated.contactName, 'Andreea Mora');
    assert.equal(hydrated.contactPhone, '+34669701069');
    assert.equal(hydrated.hubId, '1');
    assert.equal(hydrated._enrichedKey, undefined);
  });

  it('does not reuse another contact’s phone', () => {
    const cache = rememberIdentity(new Map(), {
      objectType: 'contact',
      recordId: 'C1',
      contactName: 'Dani',
      contactPhone: '+34600000001',
    });
    const hydrated = hydrateFromIdentityCache(
      { objectType: 'contact', recordId: 'C2' },
      cache,
    );
    assert.equal(hydrated.contactPhone, undefined);
    assert.equal(hydrated.recordId, 'C2');
  });

  it('lets a tab switch paint the cached phone on the first broadcast', () => {
    const cache = rememberIdentity(new Map(), {
      objectType: 'contact',
      recordId: 'C2',
      contactName: 'Andreea',
      contactPhone: '+34669701069',
    });
    const prev = {
      objectType: 'contact',
      recordId: 'C1',
      contactName: 'Dani',
      contactPhone: '+34600000001',
    };
    const plan = planPageContextUpdate(
      prev,
      hydrateFromIdentityCache({ objectType: 'contact', recordId: 'C2' }, cache),
    );
    assert.equal(plan.skipBroadcast, false);
    assert.equal(plan.context.contactName, 'Andreea');
    assert.equal(plan.context.contactPhone, '+34669701069');
  });

  it('round-trips LRU entries for session storage', () => {
    let cache = rememberIdentity(new Map(), {
      objectType: 'contact',
      recordId: 'C1',
      contactPhone: '+1',
    });
    cache = rememberIdentity(cache, {
      objectType: 'contact',
      recordId: 'C2',
      contactPhone: '+2',
    });
    const restored = identityCacheFromEntries(identityCacheToEntries(cache));
    assert.equal(
      hydrateFromIdentityCache({ objectType: 'contact', recordId: 'C2' }, restored).contactPhone,
      '+2',
    );
  });
});
