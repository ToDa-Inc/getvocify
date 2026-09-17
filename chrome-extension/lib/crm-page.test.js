import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  crmConfigPath,
  crmContextPath,
  crmDisplayName,
  crmSearchPath,
  parseCrmPageUrl,
  providerFromConnections,
} from './crm-page.js';

describe('parseCrmPageUrl', () => {
  it('prefers Pipedrive over HubSpot when the host is Pipedrive', () => {
    const parsed = parseCrmPageUrl('https://vocify2.pipedrive.com/deal/1');
    assert.equal(parsed.provider, 'pipedrive');
    assert.equal(parsed.objectType, 'deal');
    assert.equal(parsed.recordId, '1');
  });

  it('tags HubSpot records with provider hubspot', () => {
    const parsed = parseCrmPageUrl(
      'https://app.hubspot.com/contacts/123/record/0-3/999'
    );
    assert.equal(parsed.provider, 'hubspot');
    assert.equal(parsed.objectType, 'deal');
  });
});

describe('crm paths', () => {
  it('routes Pipedrive context and search to persons/deals', () => {
    assert.equal(crmContextPath('pipedrive', 'contact', '13'), '/crm/pipedrive/persons/13/context');
    assert.equal(crmContextPath('pipedrive', 'deal', '2'), '/crm/pipedrive/deals/2/context');
    assert.equal(crmSearchPath('pipedrive', 'contacts', 'ada'), '/crm/pipedrive/search/persons?q=ada');
    assert.equal(crmConfigPath('pipedrive'), '/crm/pipedrive/configuration');
  });

  it('keeps HubSpot paths', () => {
    assert.equal(crmContextPath('hubspot', 'contact', '13'), '/crm/hubspot/contacts/13/context');
    assert.equal(crmSearchPath('hubspot', 'contacts', 'ada'), '/crm/hubspot/search/contacts?q=ada');
  });
});

describe('providerFromConnections', () => {
  it('uses primary when set, else the only connected CRM', () => {
    assert.equal(
      providerFromConnections(
        { primary_crm_connection_id: 'p1' },
        [
          { id: 'h1', provider: 'hubspot', status: 'connected' },
          { id: 'p1', provider: 'pipedrive', status: 'connected' },
        ]
      ),
      'pipedrive'
    );
    assert.equal(
      providerFromConnections(null, [{ id: 'p1', provider: 'pipedrive', status: 'connected' }]),
      'pipedrive'
    );
  });
});

describe('crmDisplayName', () => {
  it('names Pipedrive from provider or URL', () => {
    assert.equal(crmDisplayName('pipedrive'), 'Pipedrive');
    assert.equal(crmDisplayName('https://acme.pipedrive.com/deal/1'), 'Pipedrive');
    assert.equal(crmDisplayName('hubspot'), 'HubSpot');
  });
});
