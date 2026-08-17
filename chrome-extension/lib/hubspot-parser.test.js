import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { parseHubSpotUrl, buildHubSpotUrl } from './hubspot-parser.js';

describe('parseHubSpotUrl', () => {
  it('detects an EU contact record page (trailing slash)', () => {
    const url = 'https://app-eu1.hubspot.com/contacts/147506535/record/0-1/838743906539/';
    assert.deepEqual(parseHubSpotUrl(url), {
      region: 'eu1',
      hubId: '147506535',
      objectTypeId: '0-1',
      objectType: 'contact',
      recordId: '838743906539',
    });
  });

  it('detects a contact record with query params', () => {
    const url = 'https://app-eu1.hubspot.com/contacts/147506535/record/0-1/838743906539/?origin=crmIndexPage';
    const parsed = parseHubSpotUrl(url);
    assert.equal(parsed?.objectType, 'contact');
    assert.equal(parsed?.recordId, '838743906539');
  });

  it('detects deal and company record pages', () => {
    assert.equal(
      parseHubSpotUrl('https://app-eu1.hubspot.com/contacts/147506535/record/0-3/420466980027')?.objectType,
      'deal'
    );
    assert.equal(
      parseHubSpotUrl('https://app.hubspot.com/contacts/123456/record/0-2/999')?.objectType,
      'company'
    );
  });

  it('detects legacy /contact/{id} URLs', () => {
    const parsed = parseHubSpotUrl('https://app-eu1.hubspot.com/contacts/147506535/contact/838743906539');
    assert.equal(parsed?.objectType, 'contact');
    assert.equal(parsed?.objectTypeId, '0-1');
    assert.equal(parsed?.recordId, '838743906539');
  });

  it('does not treat the contacts index as a record page', () => {
    assert.equal(
      parseHubSpotUrl('https://app-eu1.hubspot.com/contacts/147506535/objects/0-1/views/all/list'),
      null
    );
  });
});

describe('buildHubSpotUrl', () => {
  it('round-trips an EU contact record', () => {
    const parsed = parseHubSpotUrl('https://app-eu1.hubspot.com/contacts/147506535/record/0-1/838743906539/');
    assert.equal(
      buildHubSpotUrl(parsed),
      'https://app-eu1.hubspot.com/contacts/147506535/record/0-1/838743906539'
    );
  });
});
