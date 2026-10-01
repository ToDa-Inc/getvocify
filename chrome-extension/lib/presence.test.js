import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { createPresenceReporter, presenceFromUrl } from './presence.js';
import { parseCrmPageUrl } from './crm-page.js';

const at = (url) => presenceFromUrl(url, parseCrmPageUrl(url));

describe('presenceFromUrl', () => {
  it('reports a HubSpot contact record with its portal', () => {
    assert.deepEqual(at('https://app-eu1.hubspot.com/contacts/147506535/record/0-1/879829962968?eschref=x'), {
      provider: 'hubspot', object_type: 'contact', record_id: '879829962968', account_id: '147506535',
    });
  });

  it('reports deals and companies as records', () => {
    assert.equal(at('https://app.hubspot.com/contacts/1/record/0-3/55').object_type, 'deal');
    assert.equal(at('https://app.hubspot.com/contacts/1/record/0-2/56').object_type, 'company');
  });

  it('reports a Pipedrive person with its company domain', () => {
    assert.deepEqual(at('https://acme.pipedrive.com/person/42'), {
      provider: 'pipedrive', object_type: 'contact', record_id: '42', account_id: 'acme',
    });
  });

  it('reports "in the CRM, not on a record" for lists, sequences and other record types', () => {
    assert.deepEqual(at('https://app-eu1.hubspot.com/contacts/147506535/objects/0-1/views/all/list'), { provider: 'hubspot' });
    assert.deepEqual(at('https://app-eu1.hubspot.com/sequences/147506535'), { provider: 'hubspot' });
    assert.deepEqual(at('https://app.hubspot.com/contacts/1/record/0-5/9'), { provider: 'hubspot' });
    assert.deepEqual(at('https://acme.pipedrive.com/pipeline'), { provider: 'pipedrive' });
  });

  it('ignores HubSpot calling windows and frames so the record the rep came from stays', () => {
    assert.equal(at('https://app-eu1.hubspot.com/calling-integration-popup-ui/147506535'), null);
    assert.equal(at('https://app-eu1.hubspot.com/calling-cross-tab-embed/147506535/calling-remote-app'), null);
    assert.equal(at('https://app-eu1.hubspot.com/calling/147506535/twilio?subjectId=1'), null);
  });

  it('ignores pages outside the CRM apps', () => {
    for (const url of ['https://mail.google.com/x', 'https://www.hubspot.com/pricing', 'https://api.pipedrive.com/v1', 'https://knowledge.hubspot.com/a', null, '']) {
      assert.equal(at(url), null, String(url));
    }
  });
});

describe('createPresenceReporter', () => {
  const contact = { provider: 'hubspot', object_type: 'contact', record_id: '1' };

  it('sends changes at once and repeats only once per heartbeat', async () => {
    let t = 0;
    const sent = [];
    const reporter = createPresenceReporter({ send: (p) => sent.push(p), now: () => t, heartbeatMs: 1000 });
    assert.equal(reporter.report(contact), true);
    assert.equal(reporter.report(contact), false);
    t = 500;
    assert.equal(reporter.report({ provider: 'hubspot' }), true);
    assert.equal(reporter.report({ provider: 'hubspot' }), false);
    t = 1600;
    assert.equal(reporter.report({ provider: 'hubspot' }), true);
    assert.equal(reporter.report(null), false);
    assert.equal(sent.length, 3);
  });

  it('retries on the next look after a failed send', async () => {
    let fail = true;
    const sent = [];
    const reporter = createPresenceReporter({
      send: (p) => { sent.push(p); return fail ? Promise.reject(new Error('offline')) : Promise.resolve(); },
      heartbeatMs: 60_000,
    });
    reporter.report(contact);
    await new Promise((r) => setTimeout(r, 0));
    fail = false;
    assert.equal(reporter.report(contact), true);
    assert.equal(sent.length, 2);
  });
});
