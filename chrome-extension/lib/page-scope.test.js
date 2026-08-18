import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mergePageContext, planPageContextUpdate, recordScopeKey, recordingsScopeKey } from './page-scope.js';

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
      _enrichedKey: 'deal:D1',
    };
    const next = { objectType: 'deal', recordId: 'D1', region: 'eu1' };
    const { sameRecord, context } = mergePageContext(prev, next);
    assert.equal(sameRecord, true);
    assert.equal(context.dealName, 'Drive Solutions Deal');
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
